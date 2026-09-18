import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import * as api from "../api/client";
import type { ChatParams } from "../api/sse";
import { streamChat } from "../api/sse";
import type { HubDocumentInfo, Message, MessageAsk } from "../api/types";
import { type ChatState, type ChatView, chatReducer, initialState } from "./chatReducer";
import { loadSelected, saveSelected, selectionToRequestActs, toggleSource } from "./sources";
import { loadSidebarWidth, saveSidebarWidth } from "./sidebarWidth";

interface ChatContextValue {
  state: ChatState;
  /** Resolves true when the turn failed before the message reached the
   * server — the composer should then restore the typed text. */
  send: (message: string) => Promise<boolean>;
  stop: () => void;
  sendReview: (documentId: string, playbookId: string, label: string, role?: string) => Promise<void>;
  /** «Новая проверка» из раздела «Проверки» (T-0048): прикрепляет
   * библиотечный документ к новой беседе и запускает review-ход с ролью из
   * формы, не покидая раздел (живой прогресс — в строке таблицы). */
  startReviewFromSection: (
    documentId: string,
    playbookId: string,
    label: string,
    role: string,
  ) => Promise<void>;
  /** AskBlock's onPick/onFree answer to a paused review_role question
   * (T-0046): sends the picked/typed text as a plain next message — the
   * backend intercepts it via the conversation's last stored `ask` — and
   * remembers the role for the run card's "вы — {role}" line. */
  answerAsk: (ask: MessageAsk, text: string) => Promise<void>;
  askAboutDocuments: (documentIds: string[], message: string) => Promise<void>;
  askAboutAct: (shortName: string, message: string) => Promise<void>;
  startTemplate: (slug: string, title: string) => void;
  openFileReader: (docId: string) => void;
  clearFileReader: () => void;
  openReviewFor: (docId: string) => void;
  clearReviewRequest: () => void;
  openFilePicker: (source: "attach" | "ask") => void;
  closeFilePicker: () => void;
  requestFileUpload: () => void;
  attachFromLibrary: (docId: string) => Promise<HubDocumentInfo>;
  uploadFile: (file: File) => Promise<HubDocumentInfo>;
  updateDocument: (document: HubDocumentInfo) => void;
  setBanner: (banner: string) => void;
  openConversation: (id: string) => Promise<void>;
  newChat: () => void;
  removeConversation: (id: string) => Promise<void>;
  toggleSidebar: () => void;
  setView: (view: ChatView) => void;
  setSidebarWidth: (width: number) => void;
  toggleSource: (shortName: string) => void;
  setSelectedSources: (selected: string[]) => void;
  retryActs: () => Promise<void>;
  retryConversations: () => Promise<void>;
  openReviewPanel: (messageId: string) => void;
  closeReviewPanel: () => void;
  prefillComposer: (text: string) => void;
  // T-0054: намерение из меню скрепки (review|ask) для только что
  // загруженного документа; DocumentChip доигрывает его по готовности.
  setAttachIntent: (v: { docId: string; intent: "review" | "ask" }) => void;
  clearAttachIntent: () => void;
  /** AskBlock's "Другое — напишу сам": focuses the composer without
   * inserting any text (unlike prefillComposer, which requires non-empty
   * text to trigger Composer's focus effect). */
  focusComposer: () => void;
  /** Финал тура (T-0132): пульс кнопки отправки до клика или ручного ввода. */
  setComposerPulse: (on: boolean) => void;
}

const Ctx = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const inFlightRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // The session id of the currently-streaming turn, if any — set as soon as
  // it's known (from the caller's session or the "session" SSE event) and
  // cleared once the turn settles. `stop()` reads it to target the right
  // conversation without depending on `state.currentId`, which can lag a
  // render behind.
  const activeSessionRef = useRef<string | null>(null);
  // Guard-timer id for stop()'s abort fallback — cleared on a new stop() call
  // and once the turn settles, so it never fires as a no-op after `done`.
  const stopTimerRef = useRef<number | null>(null);

  const cancelActiveStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const refreshConversations = useCallback(async () => {
    dispatch({ type: "CONVERSATIONS_LOADING" });
    try {
      dispatch({ type: "SET_CONVERSATIONS", items: await api.listConversations() });
    } catch (e) {
      dispatch({
        type: "CONVERSATIONS_FAILED",
        error: e instanceof Error ? e.message : "Не удалось загрузить чаты",
      });
    }
  }, []);

  const loadActs = useCallback(async () => {
    dispatch({ type: "ACTS_LOADING" });
    try {
      const acts = await api.listActs();
      const names = acts.map((a) => a.short_name);
      const saved = loadSelected();
      const selected = saved ? saved.filter((s) => names.includes(s)) : names;
      dispatch({
        type: "SET_ACTS",
        acts: names,
        sources: acts,
        selected: selected.length ? selected : names,
      });
    } catch (e) {
      dispatch({
        type: "ACTS_FAILED",
        error: e instanceof Error ? e.message : "Не удалось загрузить источники",
      });
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
    void loadActs();
  }, [refreshConversations, loadActs]);

  const sendTurn = useCallback(
    async (
      message: string,
      command: ChatParams["command"] = null,
      sessionOverride?: string,
      templateSlug: string | null = null,
    ): Promise<boolean> => {
      if (inFlightRef.current) return false; // synchronous guard against double-submit
      inFlightRef.current = true;
      // Belt-and-suspenders: should already be null if the in-flight guard held.
      cancelActiveStream();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const user: Message = {
          id: crypto.randomUUID(),
          role: "user",
          content: message,
          citations: null,
          stopped: false,
          created_at: new Date().toISOString(),
        };
        // Capture the post-START_TURN turnId: useReducer batches, so reading
        // state.turnId right after dispatch still gives the pre-action value.
        const myTurnId = state.turnId + 1;
        dispatch({ type: "START_TURN", user });
        const acts = selectionToRequestActs(state.selectedSources, state.acts);
        let errored: string | null = null;
        // Once any SSE event arrives, the user message reached the agent and
        // was persisted — a later failure must not duplicate it back into
        // the composer. `sessionId` tracks the id assigned mid-stream so an
        // interrupted turn can re-sync from the server.
        const startSession = sessionOverride ?? state.currentId;
        activeSessionRef.current = startSession;
        let received = false;
        let sessionId = startSession;
        const outcome = await streamChat(
          { sessionId: startSession, message, acts, command, templateSlug, signal: controller.signal },
          (ev) => {
            received = true;
            if (ev.event === "session") {
              sessionId = ev.data.session_id;
              activeSessionRef.current = ev.data.session_id;
            }
            if (ev.event === "error") {
              errored = ev.data.detail || "Ошибка";
            }
            dispatch({ type: "SSE", turnId: myTurnId, ev });
          },
        );
        if (errored) {
          dispatch({ type: "TURN_FAILED", turnId: myTurnId, banner: errored });
        } else if (outcome === "done") {
          dispatch({ type: "FINISH_TURN", turnId: myTurnId });
          void refreshConversations();
        } else if (outcome === "interrupted" && sessionId && !controller.signal.aborted) {
          // The stream died before `done`: the local draft is not a finished
          // answer. Re-sync the conversation from the server (the user
          // message is persisted there) instead of finalizing the draft.
          dispatch({ type: "TURN_FAILED", turnId: myTurnId, banner: "" });
          try {
            const messages = await api.getMessages(sessionId);
            // The user may have navigated away while we awaited (navigation
            // aborts the controller) — don't yank them back.
            if (!controller.signal.aborted) {
              dispatch({ type: "OPEN_CONVERSATION", id: sessionId, messages });
            }
          } catch {
            // keep whatever local state we have; the banner below explains
          }
          if (!controller.signal.aborted) {
            dispatch({
              type: "SET_BANNER",
              banner: "Соединение прервано — ответ не был завершён. Попробуйте ещё раз.",
            });
          }
          void refreshConversations();
        } else {
          // "unauthorized": the global-401 notifier (fired inside streamChat)
          // already told AuthContext to drop to the login screen — this
          // banner is just a fallback in case that transition is delayed.
          const banner =
            outcome === "not_found"
              ? "Сессия не найдена. Нажмите «Новый чат»."
              : outcome === "unauthorized"
                ? "Сессия истекла — войдите снова."
                : outcome === "interrupted" || outcome === "network_error"
                  ? "Соединение прервано"
                  : "Ошибка сервера";
          dispatch({ type: "TURN_FAILED", turnId: myTurnId, banner });
        }
        // Restore the composer text only when the turn failed before the
        // server saw the message, and the user didn't abort it themselves.
        return errored === null && outcome !== "done" && !received && !controller.signal.aborted;
      } finally {
        inFlightRef.current = false;
        abortRef.current = null;
        activeSessionRef.current = null;
        if (stopTimerRef.current !== null) {
          window.clearTimeout(stopTimerRef.current);
          stopTimerRef.current = null;
        }
      }
    },
    [
      state.currentId,
      state.selectedSources,
      state.acts,
      state.turnId,
      refreshConversations,
      cancelActiveStream,
    ],
  );

  const send = useCallback((message: string) => sendTurn(message), [sendTurn]);

  const stop = useCallback(() => {
    const sessionId = activeSessionRef.current;
    if (!sessionId || !inFlightRef.current) return;
    dispatch({ type: "STOP_REQUESTED" });
    void api.stopChat(sessionId).catch(() => {
      // сервер мог уже завершить ход — done придёт по стриму и так
    });
    // Страховка: если done не пришёл (сервер завис) — рвём соединение,
    // дальше срабатывает существующий interrupted-ресинк.
    if (stopTimerRef.current !== null) window.clearTimeout(stopTimerRef.current);
    const controller = abortRef.current;
    stopTimerRef.current = window.setTimeout(() => {
      stopTimerRef.current = null;
      if (controller && abortRef.current === controller) controller.abort();
    }, 8000);
  }, []);

  const sendReview = useCallback(
    async (documentId: string, playbookId: string, label: string, role?: string): Promise<void> => {
      // Remembered before the turn starts (and survives START_TURN) so a
      // failed run can be retried with the same document/playbook. `turnId`
      // mirrors sendTurn's own `myTurnId` computation just below (same
      // `state` snapshot, no dispatch lands between the two reads) — it's
      // the id the *next* START_TURN will assign, letting TURN_FAILED
      // recognize this review's turn even if it fails before any
      // review_progress event.
      dispatch({
        type: "SET_REVIEW_REQUEST",
        request: { documentId, playbookId, label, turnId: state.turnId + 1, role: role ?? null },
      });
      await sendTurn(label, {
        type: "risk_review",
        document_id: documentId,
        playbook_id: playbookId,
        role: role ?? null,
      });
    },
    [sendTurn, state.turnId],
  );

  // T-0046: answers a paused "which side are you" question (AskBlock).
  // Unlike sendReview, this sends the picked/typed text as a *plain*
  // message — ChatAgent.run intercepts it by reading the conversation's
  // last stored message's `ask` field, not from anything the frontend sends
  // as a command. `ask` only carries document_id/playbook_id when replayed
  // from the DB (a reloaded conversation) — the live in-stream one doesn't,
  // so fall back to whatever sendReview already remembered for this attempt
  // (set before the ask ever fired). Same for `label`: reused when known,
  // else left empty — MessageList/ReviewRunCard fall back to a label-less
  // "Проверка" title rather than inventing a playbook name we don't have.
  const answerAsk = useCallback(
    async (ask: MessageAsk, text: string): Promise<void> => {
      dispatch({
        type: "SET_REVIEW_REQUEST",
        request: {
          documentId: ask.document_id ?? state.lastReviewRequest?.documentId ?? "",
          playbookId: ask.playbook_id ?? state.lastReviewRequest?.playbookId ?? "",
          label: state.lastReviewRequest?.label ?? "",
          turnId: state.turnId + 1,
          role: text,
        },
      });
      await sendTurn(text);
    },
    [sendTurn, state.lastReviewRequest, state.turnId],
  );

  // Запуск проверки из раздела «Проверки» (T-0048). Сам ход уходит эффектом
  // ниже — по той же причине, что pendingAsk: NEW_CHAT инкрементит turnId, и
  // sendTurn, вызванный в этом же замыкании, предсказал бы id хода по
  // устаревшему состоянию (все SSE-события отбросились бы редьюсером).
  const [pendingReview, setPendingReview] = useState<{
    sessionId: string;
    documentId: string;
    playbookId: string;
    label: string;
    role: string;
  } | null>(null);
  const startReviewFromSection = useCallback(
    async (documentId: string, playbookId: string, label: string, role: string): Promise<void> => {
      cancelActiveStream();
      const { document, session_id } = await api.attachLibraryDocument(documentId, null);
      dispatch({ type: "NEW_CHAT" });
      dispatch({ type: "DOCUMENT_ADDED", document, sessionId: session_id });
      // NEW_CHAT переключает view на "chat" — возвращаемся: пользователь
      // остаётся в разделе и видит живой прогресс строкой таблицы.
      dispatch({ type: "SET_VIEW", view: "reviews" });
      setPendingReview({ sessionId: session_id, documentId, playbookId, label, role });
    },
    [cancelActiveStream],
  );
  useEffect(() => {
    if (!pendingReview) return;
    setPendingReview(null);
    const { sessionId, documentId, playbookId, label, role } = pendingReview;
    dispatch({
      type: "SET_REVIEW_REQUEST",
      request: { documentId, playbookId, label, turnId: state.turnId + 1, role },
    });
    void sendTurn(
      label,
      { type: "risk_review", document_id: documentId, playbook_id: playbookId, role },
      sessionId,
    );
  }, [pendingReview, sendTurn, state.turnId]);

  const uploadFile = useCallback(
    async (file: File): Promise<HubDocumentInfo> => {
      const { document, session_id } = await api.uploadDocument(file, state.currentId);
      dispatch({ type: "DOCUMENT_ADDED", document, sessionId: session_id });
      return document;
    },
    [state.currentId],
  );

  // «Спросить по выбранным» с экрана «Файлы»: новый чат, прикрепить документы
  // библиотеки, отправить вопрос. Session id приходит из первого attach —
  // state.currentId обновится только после re-render, поэтому явный override.
  // Сам вопрос уходит эффектом ниже: NEW_CHAT инкрементит turnId, и sendTurn,
  // вызванный в этом же замыкании, предсказал бы id хода по устаревшему
  // состоянию — все SSE-события хода были бы отброшены редьюсером.
  const [pendingAsk, setPendingAsk] = useState<{
    sessionId: string | null;
    message: string;
    templateSlug?: string;
  } | null>(null);
  const askAboutDocuments = useCallback(
    async (documentIds: string[], message: string): Promise<void> => {
      cancelActiveStream();
      dispatch({ type: "NEW_CHAT" });
      let sessionId: string | null = null;
      for (const id of documentIds) {
        const { document, session_id } = await api.attachLibraryDocument(id, sessionId);
        sessionId = session_id;
        dispatch({ type: "DOCUMENT_ADDED", document, sessionId: session_id });
      }
      dispatch({ type: "SET_VIEW", view: "chat" });
      if (sessionId) setPendingAsk({ sessionId, message });
    },
    [cancelActiveStream],
  );
  // «Спросить по акту» с экрана «Источники»: новый чат с фильтром источников,
  // сжатым до одного акта. Выбор сохраняется и виден в чипе «Источники»
  // композера — вопрос и все последующие в этом чате ищут только по акту.
  const askAboutAct = useCallback(
    async (shortName: string, message: string): Promise<void> => {
      cancelActiveStream();
      dispatch({ type: "NEW_CHAT" });
      const selected = state.acts.includes(shortName) ? [shortName] : [];
      saveSelected(selected);
      dispatch({ type: "SET_SELECTED_SOURCES", selected });
      dispatch({ type: "SET_VIEW", view: "chat" });
      setPendingAsk({ sessionId: null, message });
    },
    [cancelActiveStream, state.acts],
  );
  useEffect(() => {
    if (!pendingAsk) return;
    setPendingAsk(null);
    void sendTurn(
      pendingAsk.message,
      null,
      pendingAsk.sessionId ?? undefined,
      pendingAsk.templateSlug ?? null,
    );
  }, [pendingAsk, sendTurn]);

  // E20: клик по карточке витрины «Шаблоны» — новый чат с template_slug;
  // агент получает поля шаблона в системный контекст и ведёт диалог сам.
  const startTemplate = useCallback(
    (slug: string, title: string) => {
      cancelActiveStream();
      dispatch({ type: "NEW_CHAT" });
      dispatch({ type: "SET_VIEW", view: "chat" });
      setPendingAsk({
        sessionId: null,
        message: `Заполним шаблон «${title}»`,
        templateSlug: slug,
      });
    },
    [cancelActiveStream],
  );

  // E20: «Открыть» на карточке готового документа — раздел «Файлы» с сразу
  // открытой читалкой; FilesView заберёт id и сбросит его clearFileReader.
  const openFileReader = useCallback(
    (docId: string) => dispatch({ type: "OPEN_FILE_READER", docId }),
    [],
  );
  const clearFileReader = useCallback(() => dispatch({ type: "CLEAR_FILE_READER" }), []);

  // T-0148: «Проверить на риски» из «Файлов» — раздел «Проверки» с открытым
  // диалогом и уже выбранным документом; ReviewsView заберёт id и сбросит его.
  const openReviewFor = useCallback(
    (docId: string) => dispatch({ type: "OPEN_REVIEW_REQUEST", docId }),
    [],
  );
  const clearReviewRequest = useCallback(
    () => dispatch({ type: "CLEAR_REVIEW_REQUEST" }),
    [],
  );

  // E20: пикер «Из моих файлов» (меню скрепки / ask-кнопка агента).
  const openFilePicker = useCallback(
    (source: "attach" | "ask") => dispatch({ type: "OPEN_FILE_PICKER", source }),
    [],
  );
  const closeFilePicker = useCallback(() => dispatch({ type: "CLOSE_FILE_PICKER" }), []);
  // E20: ask-кнопка «Загрузить документ» — Composer открывает выбор файла.
  const requestFileUpload = useCallback(() => dispatch({ type: "REQUEST_FILE_UPLOAD" }), []);

  // E20: приложить документ библиотеки к текущей беседе (пикер). session_id
  // приходит из attach — для новой беседы это первый источник currentId
  // (тот же контракт, что у askAboutDocuments).
  const attachFromLibrary = useCallback(
    async (docId: string): Promise<HubDocumentInfo> => {
      const { document, session_id } = await api.attachLibraryDocument(docId, state.currentId);
      dispatch({ type: "DOCUMENT_ADDED", document, sessionId: session_id });
      return document;
    },
    [state.currentId],
  );

  const updateDocument = useCallback((document: HubDocumentInfo) => {
    dispatch({ type: "DOCUMENT_UPDATED", document });
  }, []);

  const openConversation = useCallback(
    async (id: string) => {
      cancelActiveStream();
      try {
        const messages = await api.getMessages(id);
        dispatch({ type: "OPEN_CONVERSATION", id, messages });
        try {
          const documents = await api.getConversationDocuments(id);
          dispatch({ type: "SET_DOCUMENTS", documents });
        } catch {
          // Non-fatal: the conversation itself opened fine, the documents
          // panel just stays empty until the next successful reload.
        }
      } catch {
        // Banner-only: never touch streaming/draft state here. If a stream
        // for a DIFFERENT conversation is in flight, we must not wipe its
        // turn — late SSE events would then land on a "not streaming" state.
        dispatch({
          type: "SET_BANNER",
          banner: "Не удалось открыть чат. Попробуйте ещё раз.",
        });
      }
    },
    [cancelActiveStream],
  );

  const newChat = useCallback(() => {
    cancelActiveStream();
    dispatch({ type: "NEW_CHAT" });
  }, [cancelActiveStream]);

  const removeConversation = useCallback(
    async (id: string) => {
      if (state.currentId === id) cancelActiveStream();
      try {
        await api.deleteConversation(id);
      } catch {
        // Banner-only: never touch streaming/draft state here. If a stream
        // for a DIFFERENT conversation is in flight, TURN_FAILED would wipe
        // its turn and late SSE events would land on a "not streaming" state.
        dispatch({
          type: "SET_BANNER",
          banner: "Не удалось удалить чат.",
        });
        return;
      }
      if (state.currentId === id) dispatch({ type: "NEW_CHAT" });
      await refreshConversations();
    },
    [state.currentId, refreshConversations, cancelActiveStream],
  );

  const setBanner = useCallback((banner: string) => dispatch({ type: "SET_BANNER", banner }), []);

  const openReviewPanel = useCallback(
    (messageId: string) => dispatch({ type: "OPEN_REVIEW_PANEL", messageId }),
    [],
  );

  const closeReviewPanel = useCallback(() => dispatch({ type: "CLOSE_REVIEW_PANEL" }), []);

  const prefillComposer = useCallback(
    (text: string) => dispatch({ type: "PREFILL_COMPOSER", text }),
    [],
  );

  const focusComposer = useCallback(() => dispatch({ type: "FOCUS_COMPOSER" }), []);
  const setComposerPulse = useCallback(
    (on: boolean) => dispatch({ type: "SET_COMPOSER_PULSE", on }),
    [],
  );
  const setAttachIntent = useCallback(
    (v: { docId: string; intent: "review" | "ask" }) =>
      dispatch({ type: "SET_ATTACH_INTENT", docId: v.docId, intent: v.intent }),
    [],
  );
  const clearAttachIntent = useCallback(() => dispatch({ type: "CLEAR_ATTACH_INTENT" }), []);

  const toggleSidebar = useCallback(() => dispatch({ type: "TOGGLE_SIDEBAR" }), []);

  const setView = useCallback((view: ChatView) => dispatch({ type: "SET_VIEW", view }), []);

  const setSidebarWidth = useCallback((width: number) => {
    saveSidebarWidth(width);
    dispatch({ type: "SET_SIDEBAR_WIDTH", width });
  }, []);

  useEffect(() => {
    dispatch({ type: "SET_SIDEBAR_WIDTH", width: loadSidebarWidth() });
  }, []);

  const onToggleSource = useCallback(
    (shortName: string) => {
      const next = toggleSource(state.selectedSources, shortName);
      saveSelected(next);
      dispatch({ type: "SET_SELECTED_SOURCES", selected: next });
    },
    [state.selectedSources],
  );

  // Групповой выбор в селекторе источников (E09): выставить весь список разом.
  const onSetSelectedSources = useCallback((selected: string[]) => {
    saveSelected(selected);
    dispatch({ type: "SET_SELECTED_SOURCES", selected });
  }, []);

  const value = useMemo<ChatContextValue>(
    () => ({
      state,
      send,
      stop,
      sendReview,
      startReviewFromSection,
      answerAsk,
      askAboutDocuments,
      askAboutAct,
      startTemplate,
      openFileReader,
      clearFileReader,
      openReviewFor,
      clearReviewRequest,
      openFilePicker,
      closeFilePicker,
      requestFileUpload,
      attachFromLibrary,
      uploadFile,
      updateDocument,
      setBanner,
      openConversation,
      newChat,
      removeConversation,
      toggleSidebar,
      setView,
      setSidebarWidth,
      toggleSource: onToggleSource,
      setSelectedSources: onSetSelectedSources,
      retryActs: loadActs,
      retryConversations: refreshConversations,
      openReviewPanel,
      closeReviewPanel,
      prefillComposer,
      focusComposer,
      setComposerPulse,
      setAttachIntent,
      clearAttachIntent,
    }),
    [
      state,
      send,
      stop,
      sendReview,
      startReviewFromSection,
      answerAsk,
      askAboutDocuments,
      askAboutAct,
      startTemplate,
      openFileReader,
      clearFileReader,
      openReviewFor,
      clearReviewRequest,
      openFilePicker,
      closeFilePicker,
      requestFileUpload,
      attachFromLibrary,
      uploadFile,
      updateDocument,
      setBanner,
      openConversation,
      newChat,
      removeConversation,
      toggleSidebar,
      setView,
      setSidebarWidth,
      onToggleSource,
      onSetSelectedSources,
      loadActs,
      refreshConversations,
      openReviewPanel,
      closeReviewPanel,
      prefillComposer,
      focusComposer,
      setComposerPulse,
      setAttachIntent,
      clearAttachIntent,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChat(): ChatContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useChat outside ChatProvider");
  return v;
}
