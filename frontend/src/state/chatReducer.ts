import type {
  AskEventData,
  Citation,
  Conversation,
  DocumentReadyData,
  HubDocumentInfo,
  Message,
  MessageAsk,
  Act,
  ReviewProgress,
  ReviewReport,
  ServerEvent,
  TemplateDraftData,
  WebSource,
} from "../api/types";
import { SIDEBAR_DEFAULT_WIDTH } from "./sidebarWidth";

export type ResourceStatus = "idle" | "loading" | "ready" | "error";

export type ChatView = "chat" | "sources" | "files" | "reviews" | "templates";

function initialSidebarCollapsed(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 760px)").matches
  );
}

export interface ChatState {
  conversations: Conversation[];
  currentId: string | null;
  messages: Message[];
  streaming: boolean;
  // True from STOP_REQUESTED until the turn finishes — drives the composer's
  // stop-button disabled state (Task 7) and guards ChatContext.stop() against
  // a second POST on a double click.
  stopping: boolean;
  // Set by the "done" SSE event's `stopped` flag; consumed by FINISH_TURN to
  // decide whether to skip an empty assistant message and to tag a
  // partial one as `stopped: true`.
  draftStopped: boolean;
  working: { label: string } | null;
  draftAnswer: string;
  draftCitations: Citation[];
  draftWebSources: WebSource[];
  // Set by a "review_report" SSE event; attached to the finalized assistant
  // message on FINISH_TURN, mirroring draftCitations/draftWebSources.
  draftReview: ReviewReport | null;
  // Set by an "ask" SSE event: T-0046's risk_review pause (kind
  // "review_role", asks which side of the contract the user is) or T-0051's
  // plain clarifying question from any turn (kind "ask_user", answered by
  // sending a normal message). FINISH_TURN folds it into the finalized
  // message as a `MessageAsk`-shaped object carrying that same kind —
  // mirrors draftReview. The event carries no document_id/playbook_id
  // (unlike the persisted MessageAsk replayed from
  // `GET /conversations/{id}/messages`); AskBlock doesn't need them, it only
  // sends the picked/typed text as a plain next message.
  draftAsk: AskEventData | null;
  // E20: карточки шаблонного флоу текущего хода — сводка staged-черновика и
  // готовый документ; на FINISH_TURN складываются в финализированное
  // сообщение (template_draft / template_doc), зеркаля draftReview.
  draftTemplateDraft: TemplateDraftData | null;
  draftTemplateDoc: DocumentReadyData | null;
  // E20: «Открыть» на карточке документа — вид «Файлы» с сразу открытой
  // читалкой этого документа; FilesView потребляет id и сбрасывает его.
  filesReaderDocId: string | null;
  // T-0148: «Проверить на риски» из «Файлов» — раздел «Проверки» с открытым
  // диалогом и уже выбранным документом; ReviewsView заберёт id и сбросит его.
  reviewRequestDocId: string | null;
  // E20: пикер «Из моих файлов» — открыт из меню скрепки (attach) или из
  // ask-кнопки агента (ask; после приложения уходит ответное сообщение).
  filePicker: "attach" | "ask" | null;
  // E20: ask-кнопка «Загрузить документ» — монотонный счётчик, Composer
  // открывает свой выбор файла на каждый инкремент (паттерн focusToken).
  uploadRequestToken: number;
  // True while the most recent tool call was a web tool — drives the progress
  // label so web_search/web_fetch don't read as "nothing found" (they return
  // web sources, not corpus articles).
  toolIsWeb: boolean;
  pendingUser: Message | null;
  acts: string[];
  // Полные записи /acts (kind/branch) — для группировки в селекторе источников.
  actsFull: Act[];
  documents: HubDocumentInfo[];
  reviewProgress: ReviewProgress | null;
  // Id of the assistant message whose risk report is open in the side panel
  // (Task 2); null = panel closed.
  reviewPanelFor: string | null;
  // T-0054: намерение, выбранное в меню скрепки ДО загрузки файла; после
  // загрузки доигрывается (review — авто-открытие плейбуков на чипе).
  attachIntent: { docId: string; intent: "review" | "ask" } | null;
  // Set by ChatContext.sendReview right before a review turn starts — lets
  // the panel offer "retry" with the same document/playbook after a failure,
  // without threading extra args through START_TURN. `turnId` is the id the
  // *next* START_TURN will assign (mirrors sendTurn's `myTurnId` — see
  // ChatContext.sendReview); TURN_FAILED compares against it directly so a
  // review failure is recognized even if it happens before any
  // review_progress event arrived (e.g. "document not found", which fires
  // before progress).
  lastReviewRequest: {
    documentId: string;
    playbookId: string;
    label: string;
    turnId: number;
    // Known once the user has answered the "which side are you" question
    // (T-0046) — drives the "вы — {role}" line in the progress/failed run
    // card. Null until then (and for the very first sendReview() call,
    // before role is known).
    role: string | null;
  } | null;
  // Set when a review turn ends in error (TURN_FAILED while a review was in
  // progress); drives the panel's failure state. Cleared on the next turn.
  reviewFailed: { detail: string } | null;
  selectedSources: string[];
  // Text queued for the composer by "Обсудить в чате" / "Обсудить риски в
  // чате" (T-0010/Задача 5) — Composer picks it up in a useEffect, inserts
  // it, focuses, and clears it back via PREFILL_COMPOSER("").
  composerPrefill: string | null;
  // Monotonic counter bumped by FOCUS_COMPOSER (T-0046: "Другое — напишу
  // сам" in AskBlock) — Composer focuses the textarea (no text change) on
  // every increment. 0 is the initial no-op value.
  composerFocusToken: number;
  // Финал тура (T-0132): кнопка отправки пульсирует «сердцебиением», пока
  // пользователь не кликнул её или не начал править текст сам.
  composerPulse: boolean;
  // Отправленные пользователем сообщения за эту сессию (T-0132): слагаемое
  // к questions_asked из MeResponse для живого автоскрытия пилюли тура.
  questionsSentInSession: number;
  banner: string | null;
  sidebarCollapsed: boolean;
  view: ChatView;
  sidebarWidth: number;
  // Monotonic per-turn id. Bumps on START_TURN, NEW_CHAT, OPEN_CONVERSATION,
  // and on removal of the currently-open conversation. SSE / FINISH_TURN /
  // TURN_FAILED actions whose `turnId` doesn't match are dropped — they are
  // leftovers from a stream the user navigated away from.
  turnId: number;
  actsStatus: ResourceStatus;
  actsError: string | null;
  conversationsStatus: ResourceStatus;
  conversationsError: string | null;
}

export const initialState: ChatState = {
  conversations: [],
  currentId: null,
  messages: [],
  streaming: false,
  stopping: false,
  draftStopped: false,
  working: null,
  draftAnswer: "",
  draftCitations: [],
  draftWebSources: [],
  draftReview: null,
  draftAsk: null,
  draftTemplateDraft: null,
  draftTemplateDoc: null,
  filesReaderDocId: null,
  reviewRequestDocId: null,
  filePicker: null,
  uploadRequestToken: 0,
  toolIsWeb: false,
  pendingUser: null,
  acts: [],
  actsFull: [],
  documents: [],
  reviewProgress: null,
  reviewPanelFor: null,
  attachIntent: null,
  lastReviewRequest: null,
  reviewFailed: null,
  selectedSources: [],
  composerPrefill: null,
  composerFocusToken: 0,
  composerPulse: false,
  questionsSentInSession: 0,
  banner: null,
  sidebarCollapsed: initialSidebarCollapsed(),
  view: "chat",
  sidebarWidth: SIDEBAR_DEFAULT_WIDTH,
  turnId: 0,
  actsStatus: "idle",
  actsError: null,
  conversationsStatus: "idle",
  conversationsError: null,
};

const WEB_TOOLS = new Set(["web_search", "web_fetch"]);

function studyingLabel(found: { number: string }[]): string {
  if (found.length === 0) return "Ничего не нашёл, уточняю запрос…";
  return `Изучаю ст. ${found.map((f) => f.number).join(", ")}…`;
}

export function applyServerEvent(state: ChatState, ev: ServerEvent): ChatState {
  switch (ev.event) {
    case "session":
      return { ...state, currentId: ev.data.session_id };
    case "reasoning":
      return state.working ? state : { ...state, working: { label: "Думаю" } };
    case "tool_call": {
      const web = WEB_TOOLS.has(ev.data.tool);
      return {
        ...state,
        toolIsWeb: web,
        working: { label: web ? "Ищу в интернете…" : "Ищу в законодательстве…" },
      };
    }
    case "tool_result":
      // Web tools report sources via the separate `web_sources` event, not via
      // `found` (which only carries corpus articles) — so never show
      // "nothing found" for them.
      return {
        ...state,
        working: {
          label: state.toolIsWeb ? "Просматриваю источники из интернета…" : studyingLabel(ev.data.found),
        },
      };
    case "reset_delta":
      return { ...state, draftAnswer: "", working: null, draftCitations: [], draftWebSources: [] };
    case "delta":
      return { ...state, working: null, draftAnswer: state.draftAnswer + ev.data.text };
    case "citations":
      return { ...state, draftCitations: ev.data.articles };
    case "web_sources":
      return { ...state, draftWebSources: ev.data.sources };
    case "review_progress": {
      // Under concurrency, `running` events carry a start-order counter
      // (e.g. 4 workers → running: 1,2,3,4) while final (non-"running")
      // events carry a completion-order counter (1,2,3…) — those two
      // sequences interleave and are NOT jointly monotonic. Blindly
      // replacing reviewProgress with the latest event makes the bar's
      // numeric fraction jump forward and back. Keep the displayed index
      // monotonic: only advance it on final events (their index IS the
      // completed count); "running" events update only the visible
      // title/total, not the index.
      const prevIndex = state.reviewProgress?.index ?? 0;
      const index = ev.data.status === "running" ? prevIndex : ev.data.index;
      return { ...state, reviewProgress: { ...ev.data, index } };
    }
    case "review_report":
      return { ...state, draftReview: ev.data, reviewProgress: null };
    case "template_draft":
      return { ...state, draftTemplateDraft: ev.data, working: null };
    case "document_ready":
      return { ...state, draftTemplateDoc: ev.data, working: null };
    case "ask":
      // The backend never streams the question as a `delta` for this branch
      // (see ChatAgent.run_review) — the AskEventData.question IS the
      // message content, so mirror it into draftAnswer directly.
      return { ...state, draftAsk: ev.data, draftAnswer: ev.data.question, working: null };
    case "done":
      return { ...state, draftStopped: Boolean(ev.data.stopped) };
    case "error":
      return { ...state, banner: ev.data.detail || "Ошибка" };
    default:
      // Недостижимо по типам, но достижимо в рантайме: бэкенд может выкатить
      // новый тип SSE-события раньше фронта. Без этой ветки switch вернул бы
      // undefined, и оно стало бы ВСЕМ состоянием чата — белый экран вместо
      // одного проигнорированного события.
      return state;
  }
}

export type Action =
  | { type: "START_TURN"; user: Message }
  | { type: "SSE"; turnId: number; ev: ServerEvent }
  | { type: "FINISH_TURN"; turnId: number }
  | { type: "TURN_FAILED"; turnId: number; banner: string }
  | { type: "STOP_REQUESTED" }
  | { type: "SET_BANNER"; banner: string }
  | { type: "CONVERSATIONS_LOADING" }
  | { type: "CONVERSATIONS_FAILED"; error: string }
  | { type: "SET_CONVERSATIONS"; items: Conversation[] }
  | { type: "OPEN_CONVERSATION"; id: string; messages: Message[] }
  | { type: "NEW_CHAT" }
  | { type: "ACTS_LOADING" }
  | { type: "ACTS_FAILED"; error: string }
  | { type: "SET_ACTS"; acts: string[]; sources?: Act[]; selected: string[] }
  | { type: "SET_SELECTED_SOURCES"; selected: string[] }
  | { type: "SET_DOCUMENTS"; documents: HubDocumentInfo[] }
  | { type: "DOCUMENT_ADDED"; document: HubDocumentInfo; sessionId: string }
  | { type: "DOCUMENT_UPDATED"; document: HubDocumentInfo }
  | { type: "TOGGLE_SIDEBAR" }
  | { type: "SET_VIEW"; view: ChatView }
  | { type: "SET_SIDEBAR_WIDTH"; width: number }
  | { type: "OPEN_REVIEW_PANEL"; messageId: string }
  | { type: "CLOSE_REVIEW_PANEL" }
  | { type: "PREFILL_COMPOSER"; text: string }
  | { type: "FOCUS_COMPOSER" }
  | { type: "OPEN_FILE_READER"; docId: string }
  | { type: "CLEAR_FILE_READER" }
  | { type: "OPEN_REVIEW_REQUEST"; docId: string }
  | { type: "CLEAR_REVIEW_REQUEST" }
  | { type: "OPEN_FILE_PICKER"; source: "attach" | "ask" }
  | { type: "CLOSE_FILE_PICKER" }
  | { type: "REQUEST_FILE_UPLOAD" }
  | { type: "SET_COMPOSER_PULSE"; on: boolean }
  | { type: "SET_ATTACH_INTENT"; docId: string; intent: "review" | "ask" }
  | { type: "CLEAR_ATTACH_INTENT" }
  | {
      type: "SET_REVIEW_REQUEST";
      request: { documentId: string; playbookId: string; label: string; turnId: number; role: string | null };
    };

export function chatReducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "START_TURN":
      return {
        ...state,
        streaming: true,
        stopping: false,
        draftStopped: false,
        banner: null,
        // T-0132: заданный вопрос в этой сессии — вместе с questions_asked
        // из MeResponse скрывает пилюлю тура после третьего.
        questionsSentInSession: state.questionsSentInSession + 1,
        pendingUser: action.user,
        draftAnswer: "",
        draftCitations: [],
        draftWebSources: [],
        draftReview: null,
        draftAsk: null,
        draftTemplateDraft: null,
        draftTemplateDoc: null,
        toolIsWeb: false,
        working: null,
        reviewProgress: null,
        // Not lastReviewRequest: the following sendReview (if any) overwrites
        // it via SET_REVIEW_REQUEST; a plain send() leaves it as a stale
        // retry target, which is harmless since nothing reads it without
        // reviewFailed also being set.
        reviewFailed: null,
        reviewPanelFor: null,
        turnId: state.turnId + 1,
      };
    case "SSE":
      if (action.turnId !== state.turnId) return state;
      return applyServerEvent(state, action.ev);
    case "STOP_REQUESTED":
      return state.streaming ? { ...state, stopping: true } : state;
    case "FINISH_TURN": {
      if (action.turnId !== state.turnId) return state;
      const finalized: Message[] = [...state.messages];
      if (state.pendingUser) finalized.push(state.pendingUser);
      const skipAssistant =
        state.draftStopped &&
        state.draftAnswer === "" &&
        !state.draftReview &&
        !state.draftAsk &&
        !state.draftTemplateDraft &&
        !state.draftTemplateDoc;
      if (!skipAssistant) {
        finalized.push({
          id: crypto.randomUUID(),
          role: "assistant",
          content: state.draftAnswer,
          citations: state.draftCitations.length ? state.draftCitations : null,
          web_sources: state.draftWebSources.length ? state.draftWebSources : null,
          review: state.draftReview,
          // T-0046: the "ask" SSE event carries only question/options (no
          // document_id/playbook_id — those live on the persisted MessageAsk
          // replayed from the DB after a reload). AskBlock's buttons don't
          // need them: the picked/typed answer is just the next plain
          // message, and the backend intercepts it via the *stored* ask.
          ask: state.draftAsk
            ? ({
                // T-0051: живой ask несёт свой kind (review_role | ask_user)
                kind: state.draftAsk.kind ?? "review_role",
                question: state.draftAsk.question,
                options: state.draftAsk.options ?? [],
                // E20: признак шаблонного вопроса — гейт перехвата кнопок
                template: state.draftAsk.template ?? false,
              } satisfies MessageAsk)
            : null,
          template_draft: state.draftTemplateDraft,
          template_doc: state.draftTemplateDoc,
          stopped: state.draftStopped,
          created_at: new Date().toISOString(),
        });
      }
      return {
        ...state,
        streaming: false,
        stopping: false,
        draftStopped: false,
        working: null,
        messages: finalized,
        pendingUser: null,
        draftAnswer: "",
        draftCitations: [],
        draftWebSources: [],
        draftReview: null,
        draftAsk: null,
        draftTemplateDraft: null,
        draftTemplateDoc: null,
        toolIsWeb: false,
        reviewProgress: null,
      };
    }
    case "TURN_FAILED":
      if (action.turnId !== state.turnId) return state;
      return {
        ...state,
        streaming: false,
        stopping: false,
        draftStopped: false,
        working: null,
        pendingUser: null,
        draftAnswer: "",
        draftCitations: [],
        draftWebSources: [],
        draftReview: null,
        draftAsk: null,
        draftTemplateDraft: null,
        draftTemplateDoc: null,
        toolIsWeb: false,
        banner: action.banner,
        reviewProgress: null,
        // Keyed on turnId, not on whether a review_progress event already
        // arrived: an early pipeline failure ("Документ не найден", "Сервис
        // документов недоступен") fires *before* the first progress event,
        // so gating on reviewProgress !== null missed it entirely. Comparing
        // the failed turn's id against lastReviewRequest.turnId (set by
        // sendReview for the turn it's about to start) correctly recognizes
        // any failure of that review turn, progress or not — while a plain
        // chat turn failing after an earlier review request still can't
        // match (its turnId has moved on).
        reviewFailed:
          state.lastReviewRequest !== null && state.lastReviewRequest.turnId === action.turnId
            ? { detail: action.banner }
            : state.reviewFailed,
      };
    case "SET_BANNER":
      return { ...state, banner: action.banner };
    case "CONVERSATIONS_LOADING":
      return { ...state, conversationsStatus: "loading", conversationsError: null };
    case "CONVERSATIONS_FAILED":
      return { ...state, conversationsStatus: "error", conversationsError: action.error };
    case "SET_CONVERSATIONS":
      return {
        ...state,
        conversations: action.items,
        conversationsStatus: "ready",
        conversationsError: null,
      };
    case "OPEN_CONVERSATION":
      return {
        ...state,
        currentId: action.id,
        messages: action.messages,
        banner: null,
        pendingUser: null,
        draftAnswer: "",
        draftCitations: [],
        draftWebSources: [],
        draftReview: null,
        draftAsk: null,
        draftTemplateDraft: null,
        draftTemplateDoc: null,
        filePicker: null,
        toolIsWeb: false,
        streaming: false,
        stopping: false,
        draftStopped: false,
        working: null,
        view: "chat",
        turnId: state.turnId + 1,
        reviewProgress: null,
        reviewPanelFor: null,
        reviewFailed: null,
        lastReviewRequest: null,
        attachIntent: null,
      };
    case "NEW_CHAT":
      return {
        ...state,
        currentId: null,
        messages: [],
        banner: null,
        pendingUser: null,
        draftAnswer: "",
        draftCitations: [],
        draftWebSources: [],
        draftReview: null,
        draftAsk: null,
        draftTemplateDraft: null,
        draftTemplateDoc: null,
        filePicker: null,
        toolIsWeb: false,
        streaming: false,
        stopping: false,
        draftStopped: false,
        working: null,
        view: "chat",
        turnId: state.turnId + 1,
        documents: [],
        reviewProgress: null,
        reviewPanelFor: null,
        reviewFailed: null,
        lastReviewRequest: null,
        attachIntent: null,
      };
    case "ACTS_LOADING":
      return { ...state, actsStatus: "loading", actsError: null };
    case "ACTS_FAILED":
      return { ...state, actsStatus: "error", actsError: action.error };
    case "SET_ACTS":
      return {
        ...state,
        acts: action.acts,
        actsFull: action.sources ?? state.actsFull,
        selectedSources: action.selected,
        actsStatus: "ready",
        actsError: null,
      };
    case "SET_SELECTED_SOURCES":
      return { ...state, selectedSources: action.selected };
    case "SET_DOCUMENTS":
      return { ...state, documents: action.documents };
    case "DOCUMENT_ADDED":
      return {
        ...state,
        documents: [...state.documents, action.document],
        currentId: state.currentId ?? action.sessionId,
      };
    case "DOCUMENT_UPDATED":
      return {
        ...state,
        documents: state.documents.map((d) =>
          d.id === action.document.id ? action.document : d,
        ),
      };
    case "TOGGLE_SIDEBAR":
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed };
    case "SET_VIEW":
      return { ...state, view: action.view };
    case "SET_SIDEBAR_WIDTH":
      return { ...state, sidebarWidth: action.width };
    case "OPEN_REVIEW_PANEL":
      return { ...state, reviewPanelFor: action.messageId };
    case "CLOSE_REVIEW_PANEL":
      return { ...state, reviewPanelFor: null };
    case "PREFILL_COMPOSER":
      return { ...state, composerPrefill: action.text || null };
    case "OPEN_FILE_READER":
      return { ...state, view: "files", filesReaderDocId: action.docId };
    case "CLEAR_FILE_READER":
      return state.filesReaderDocId === null ? state : { ...state, filesReaderDocId: null };
    case "OPEN_REVIEW_REQUEST":
      return { ...state, view: "reviews", reviewRequestDocId: action.docId };
    case "CLEAR_REVIEW_REQUEST":
      return state.reviewRequestDocId === null
        ? state
        : { ...state, reviewRequestDocId: null };
    case "OPEN_FILE_PICKER":
      return { ...state, filePicker: action.source };
    case "CLOSE_FILE_PICKER":
      return state.filePicker === null ? state : { ...state, filePicker: null };
    case "REQUEST_FILE_UPLOAD":
      return { ...state, uploadRequestToken: state.uploadRequestToken + 1 };
    case "SET_ATTACH_INTENT":
      return { ...state, attachIntent: { docId: action.docId, intent: action.intent } };
    case "CLEAR_ATTACH_INTENT":
      return state.attachIntent === null ? state : { ...state, attachIntent: null };
    case "FOCUS_COMPOSER":
      return { ...state, composerFocusToken: state.composerFocusToken + 1 };
    case "SET_COMPOSER_PULSE":
      return state.composerPulse === action.on ? state : { ...state, composerPulse: action.on };
    case "SET_REVIEW_REQUEST":
      return { ...state, lastReviewRequest: action.request };
  }
}
