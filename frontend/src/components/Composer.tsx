import {
  ArrowUp,
  BookOpen,
  FileCheck,
  FolderOpen,
  MessageSquare,
  Paperclip,
  Search,
  Square,
  SquareCheckBig,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

/* Готовые команды пустого Home: клик кладёт заготовку в композер. */
const HOME_COMMANDS = [
  {
    icon: FileCheck,
    title: "Проверка договора",
    desc: "Риски документа со ссылками на нормы",
    text: "Проверь приложенный договор на риски",
  },
  {
    icon: Search,
    title: "Поиск нормы",
    desc: "Применимые статьи по описанию ситуации",
    text: "Какие нормы регулируют ",
  },
  {
    icon: BookOpen,
    title: "Разъяснение статьи",
    desc: "Как норма применяется на практике",
    text: "Разъясни, как применяется статья ",
  },
  {
    icon: MessageSquare,
    title: "Ответ на претензию",
    desc: "Черновик ответа по вашей переписке",
    text: "Составь черновик ответа на претензию: ",
  },
];
import { MAX_MESSAGE_CHARS } from "../api/types";
import { useChat } from "../state/ChatContext";
import { IconButton } from "../ui";
import { DocumentChip } from "./DocumentChip";
import { SourceSelector } from "./SourceSelector";

export function Composer({ centered = false }: { centered?: boolean }) {
  const {
    state,
    send,
    stop,
    uploadFile,
    setBanner,
    prefillComposer,
    setAttachIntent,
    openFilePicker,
    setComposerPulse,
  } = useChat();
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [uploading, setUploading] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Скрепка 2.0 (T-0054): намерение выбирается ДО файла — клик по скрепке
  // раскрывает меню сценариев, пункт запоминает интент и открывает выбор
  // файла; после загрузки интент доигрывается (review — авто-открытие
  // плейбуков на чипе, ask — фокус сюда).
  const [attachOpen, setAttachOpen] = useState(false);
  const attachIntent = useRef<"review" | "ask" | null>(null);
  const attachRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!attachOpen) return;
    const onDown = (e: MouseEvent) => {
      if (attachRef.current && !attachRef.current.contains(e.target as Node)) setAttachOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAttachOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [attachOpen]);

  const pickWithIntent = (intent: "review" | "ask") => {
    attachIntent.current = intent;
    setAttachOpen(false);
    fileRef.current?.click();
  };

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file after an error
    const intent = attachIntent.current;
    attachIntent.current = null;
    if (!file) return;
    setUploading(true);
    try {
      const doc = await uploadFile(file);
      if (intent) setAttachIntent({ docId: doc.id, intent });
      if (intent === "ask") ref.current?.focus();
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Не удалось загрузить документ");
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [text]);

  // Auto-focus on mount so a new chat is ready to type immediately; the
  // accent edge stays quiet until there is text (red = action, not default).
  useEffect(() => {
    ref.current?.focus();
  }, []);

  // «Обсудить в чате» / «Обсудить риски в чате» (T-0010/Задача 5): the panel
  // queues text via prefillComposer(text) and closes itself; this effect
  // picks it up, inserts + focuses, then clears composerPrefill so it
  // doesn't refire on the next unrelated render.
  useEffect(() => {
    const prefill = state.composerPrefill;
    if (!prefill) return;
    setText(prefill);
    prefillComposer("");
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  }, [state.composerPrefill, prefillComposer]);

  // AskBlock's "Другое — напишу сам" (T-0046): focuses the composer without
  // inserting any text — prefillComposer("") wouldn't fire this effect
  // (composerPrefill would just stay/become null, no dependency change), so
  // this is a dedicated monotonic counter bumped by ChatContext.focusComposer.
  useEffect(() => {
    if (!state.composerFocusToken) return;
    ref.current?.focus();
  }, [state.composerFocusToken]);

  // E20: ask-кнопка «Загрузить документ» — открывает системный выбор файла
  // здесь (свой input у композера); интент "ask" — после загрузки фокус сюда.
  useEffect(() => {
    if (!state.uploadRequestToken) return;
    attachIntent.current = "ask";
    fileRef.current?.click();
  }, [state.uploadRequestToken]);

  const insertHint = (value: string) => {
    setText(value);
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  };

  const tooLong = text.length > MAX_MESSAGE_CHARS;
  const canSend = !state.streaming && text.trim() !== "" && !tooLong;
  const submit = () => {
    if (!canSend) return;
    if (state.composerPulse) setComposerPulse(false);
    const message = text.trim();
    setText("");
    void send(message).then((restore) => {
      // The turn failed before the server saw the message — give the text
      // back instead of losing it, unless the user already typed new text.
      if (restore) setText((current) => current || message);
    });
  };

  // Accent edge only when there is content to send; bare focus gets a quieter
  // gray step (see .composer-box-focused). Streaming must not light it up:
  // red = action, and the stream state is already shown by the working line.
  const active = text.trim() !== "";

  // Clicking anywhere inside the box focuses the input — except on the textarea
  // itself (native caret placement) and the interactive controls (pill / send).
  const focusFromBox = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target === ref.current || target.closest("button, .source-selector")) return;
    e.preventDefault();
    ref.current?.focus();
  };

  return (
    <div className={centered ? "composer composer-centered" : "composer"}>
      {state.documents.length > 0 && (
        <div className="doc-strip">
          {state.documents.map((d) => (
            <DocumentChip key={d.id} document={d} />
          ))}
        </div>
      )}
      <div
        className={`composer-box${focused ? " composer-box-focused" : ""}${active ? " composer-box-active" : ""}`}
      >
        <div className="composer-bloom" aria-hidden />
        {/* Якорь тура — на элементе с видимым скруглением (--r-composer-outer):
            вырез снимает радиус с computed style цели (T-0132). */}
        <div className="composer-frame" data-tour="composer">
          <div className="composer-inner" onMouseDown={focusFromBox}>
            <textarea
              ref={ref}
              rows={1}
              value={text}
              aria-label="Ваш запрос"
              placeholder="Юридический поиск, анализ и формулировки"
              onChange={(e) => {
                setText(e.target.value);
                // Ручной ввод снимает пульс финала тура (T-0132).
                if (state.composerPulse) setComposerPulse(false);
              }}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="composer-row">
              <input
                ref={fileRef}
                type="file"
                accept=".docx,.pdf"
                hidden
                onChange={onPickFile}
              />
              <div className="composer-left">
                <div className="attach-wrap" ref={attachRef}>
                  <IconButton
                    className="composer-attach"
                    icon={<Paperclip size={18} className="attach-clip-icon" />}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setAttachOpen((v) => !v)}
                    disabled={uploading}
                    loading={uploading}
                    aria-label="Прикрепить документ"
                    aria-haspopup="menu"
                    aria-expanded={attachOpen}
                  />
                  {attachOpen && (
                    <div className="attach-menu" role="menu">
                      <button
                        type="button"
                        className="attach-item"
                        role="menuitem"
                        onClick={() => pickWithIntent("review")}
                      >
                        <SquareCheckBig size={15} className="attach-item-icon" />
                        <span className="attach-item-text">
                          Проверить на риски
                          <small>Отчет со ссылками на нормы права</small>
                        </span>
                      </button>
                      <button
                        type="button"
                        className="attach-item"
                        role="menuitem"
                        onClick={() => pickWithIntent("ask")}
                      >
                        <MessageSquare size={15} className="attach-item-icon" />
                        <span className="attach-item-text">
                          Задать вопрос по документу
                          <small>Ответы по тексту документа</small>
                        </span>
                      </button>
                      <button
                        type="button"
                        className="attach-item"
                        role="menuitem"
                        onClick={() => {
                          setAttachOpen(false);
                          openFilePicker("attach");
                        }}
                      >
                        <FolderOpen size={15} className="attach-item-icon" />
                        <span className="attach-item-text">
                          Из моих файлов
                          <small>Приложить документ из библиотеки</small>
                        </span>
                      </button>
                    </div>
                  )}
                </div>
                <SourceSelector />
              </div>
              {tooLong && (
                <span className="composer-limit" role="alert">
                  Слишком длинное сообщение: {text.length.toLocaleString("ru-RU")} /{" "}
                  {MAX_MESSAGE_CHARS.toLocaleString("ru-RU")}
                </span>
              )}
              {state.streaming ? (
                <IconButton
                  className="send"
                  view="primary"
                  icon={<Square size={14} fill="currentColor" />}
                  disabled={state.stopping}
                  onClick={stop}
                  aria-label="Остановить генерацию"
                />
              ) : (
                <IconButton
                  className={state.composerPulse && canSend ? "send tour-send-pulse" : "send"}
                  view="primary"
                  icon={<ArrowUp size={18} />}
                  disabled={!canSend}
                  onClick={submit}
                  aria-label="Отправить"
                />
              )}
            </div>
          </div>
        </div>
      </div>
      {centered && (
        <div className="home-cmds">
          {HOME_COMMANDS.map((cmd) => (
            <button
              key={cmd.title}
              type="button"
              className="home-cmd"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => insertHint(cmd.text)}
            >
              <cmd.icon size={17} strokeWidth={1.7} aria-hidden="true" />
              <span className="home-cmd-t">{cmd.title}</span>
              <span className="home-cmd-s">{cmd.desc}</span>
            </button>
          ))}
        </div>
      )}
      <p className="disclaimer">Ответы генерирует нейросеть. Она может ошибаться.</p>
    </div>
  );
}
