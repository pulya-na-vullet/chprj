import { MessageSquare, SquareCheckBig } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as api from "../api/client";
import type { HubDocumentInfo, PlaybookInfo } from "../api/types";
import { useChat } from "../state/ChatContext";
import { FileTypeIcon } from "./files/FileTypeIcon";

// Module-level cache: the playbook list is small and static for a session, so
// the first opened menu fetches it and every chip afterwards reuses the result.
let playbooksPromise: Promise<PlaybookInfo[]> | null = null;
function loadPlaybooks(): Promise<PlaybookInfo[]> {
  if (!playbooksPromise)
    playbooksPromise = api.listPlaybooks().catch((err) => {
      playbooksPromise = null; // don't cache a failure — allow a retry
      throw err;
    });
  return playbooksPromise;
}

export function DocumentChip({ document: doc }: { document: HubDocumentInfo }) {
  const { state, sendReview, updateDocument, focusComposer, clearAttachIntent } = useChat();
  const [open, setOpen] = useState(false);
  const [menuScreen, setMenuScreen] = useState<"scenario" | "playbooks">("scenario");
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const failed = doc.status === "failed";
  const processing = doc.status === "processing";
  const ready = doc.status === "ready";

  // Close on outside click / Escape, mirroring SourceSelector's menu behaviour.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Documents attach as "processing" while the hub extracts text — poll until
  // the status settles so the chip unlocks (or shows the failure) without a
  // manual refresh.
  useEffect(() => {
    if (doc.status !== "processing") return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const fresh = await api.getDocument(doc.id);
        if (alive && fresh.status !== "processing") {
          updateDocument(fresh);
        }
      } catch {
        /* transient — keep polling */
      }
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [doc.id, doc.status, updateDocument]);

  const toggle = () => {
    if (!ready) return; // only a fully-processed document can be reviewed
    const next = !open;
    setOpen(next);
    if (next) setMenuScreen("scenario");
  };

  const showPlaybooks = () => {
    setMenuScreen("playbooks");
    if (playbooks === null) {
      // Сброс прошлой ошибки перед (ре)загрузкой: провал не кэшируется, и
      // без сброса успешный ретрай отрисовал бы список под старым баннером.
      setError(null);
      loadPlaybooks()
        .then((items) => setPlaybooks(items))
        .catch(() => setError("Не удалось загрузить плейбуки"));
    }
  };

  const askAboutDocument = () => {
    setOpen(false);
    focusComposer();
  };

  // T-0054: намерение из меню скрепки. Когда «его» документ дозрел до ready,
  // «Проверить на риски» сам открывает выбор плейбука; ask от чипа ничего
  // не требует (фокус в композер поставлен ещё при загрузке) — интент просто
  // гасится.
  useEffect(() => {
    const pending = state.attachIntent;
    if (!pending || pending.docId !== doc.id || doc.status !== "ready") return;
    clearAttachIntent();
    if (pending.intent !== "review") return;
    setOpen(true);
    showPlaybooks();
    // showPlaybooks стабильна по содержимому (сеттеры + модульный кэш)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.attachIntent, doc.id, doc.status, clearAttachIntent]);

  const pick = (pb: PlaybookInfo) => {
    setOpen(false);
    void sendReview(doc.id, pb.id, `Проверить «${doc.filename}»: ${pb.name}`);
  };

  return (
    <div className="doc-chip-wrap" ref={rootRef}>
      <button
        type="button"
        className={failed ? "doc-chip doc-chip-failed" : "doc-chip"}
        onClick={toggle}
        disabled={!ready || state.streaming}
        title={failed ? doc.error || "Не удалось обработать документ" : doc.filename}
        aria-haspopup={ready ? "menu" : undefined}
        aria-expanded={ready ? open : undefined}
      >
        <FileTypeIcon parser={doc.parser} />
        <span className="doc-chip-name">{doc.filename}</span>
        {processing && <span className="doc-chip-status">обрабатывается…</span>}
        {failed && <span className="doc-chip-err">ошибка</span>}
      </button>
      {/* T-0053: без head с именем файла — оно уже на чипе под меню;
          меню шире, чтобы пункты не переносились. */}
      {open && ready && menuScreen === "scenario" && (
        <div className="doc-menu doc-menu-scenario" role="menu">
          <button
            type="button"
            className="doc-menu-item doc-menu-item-scenario"
            role="menuitem"
            onClick={showPlaybooks}
          >
            <SquareCheckBig size={15} className="doc-menu-item-icon" />
            <span className="doc-menu-item-text">
              Проверить на риски
              <small>Отчет со ссылками на нормы права</small>
            </span>
          </button>
          <button
            type="button"
            className="doc-menu-item doc-menu-item-scenario"
            role="menuitem"
            onClick={askAboutDocument}
          >
            <MessageSquare size={15} className="doc-menu-item-icon" />
            <span className="doc-menu-item-text">
              Задать вопрос по документу
              <small>Ответы по тексту документа</small>
            </span>
          </button>
        </div>
      )}
      {open && ready && menuScreen === "playbooks" && (
        <div className="doc-menu" role="menu">
          <div className="doc-menu-head">Проверить на риски</div>
          {error && <div className="doc-menu-status">{error}</div>}
          {!error && playbooks === null && <div className="doc-menu-status">Загружаю…</div>}
          {!error && playbooks?.length === 0 && (
            <div className="doc-menu-status">Нет доступных плейбуков</div>
          )}
          {playbooks?.map((pb) => (
            <button
              type="button"
              key={pb.id}
              className="doc-menu-item"
              role="menuitem"
              onClick={() => pick(pb)}
            >
              <span className="doc-menu-item-name">{pb.name}</span>
              <span className="doc-menu-item-count">{pb.rules_count} правил</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
