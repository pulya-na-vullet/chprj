import { ArrowUp, LayoutGrid, List, MessageCircle, Search, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../../api/client";
import type { HubDocumentInfo } from "../../api/types";
import { useChat } from "../../state/ChatContext";
import { IconButton } from "../../ui";
import { DeleteDialog } from "./DeleteDialog";
import { DocMenu } from "./DocMenu";
import { FileCard } from "./FileCard";
import { FilesReader } from "./FilesReader";
import { FileTypeIcon } from "./FileTypeIcon";
import { StatusPill } from "./StatusPill";
import { filterDocuments } from "./filter";
import { formatDate, formatSize, humanizeDocError, summaryLabel } from "./format";
import { loadViewMode, saveViewMode, type FilesViewMode } from "./viewMode";

const ALLOWED = [".docx", ".pdf"];
const MAX_BYTES = 20 * 1024 * 1024;
const PANEL_CLOSE_MS = 240;

function validate(file: File): string | null {
  const lower = file.name.toLowerCase();
  if (!ALLOWED.some((ext) => lower.endsWith(ext))) return "Поддерживаются только файлы .docx и .pdf";
  if (file.size > MAX_BYTES) return "Файл больше 20 МБ";
  return null;
}

export function FilesView() {
  const { askAboutDocuments, state: chatState, clearFileReader, openReviewFor } = useChat();
  const [docs, setDocs] = useState<HubDocumentInfo[] | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [panelShown, setPanelShown] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<HubDocumentInfo | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<FilesViewMode>(loadViewMode);
  const inputRef = useRef<HTMLInputElement>(null);
  // Minor 9 (финальное ревью): фокус после «Спросить в чате» — тот же
  // input, что и поиск, переключается по askMode.
  const stripInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panelRef = useRef<HTMLElement>(null);

  const load = () => {
    setError(false);
    setDocs(null);
    api.listDocuments().then(setDocs).catch(() => setError(true));
  };
  useEffect(load, []);

  // Poll while any document is still processing, or a fresh ready document
  // is still waiting for its server-side «Суть» to catch up (5-минутная
  // отсечка — не поллить вечно, если LLM на сервере выключен).
  const hasProcessing = !!docs?.some((d) => d.status === "processing");
  const AWAIT_SUMMARY_MS = 5 * 60 * 1000;
  const awaitingSummary = !!docs?.some(
    (d) =>
      d.status === "ready" &&
      !d.summary &&
      Date.now() - new Date(d.created_at).getTime() < AWAIT_SUMMARY_MS,
  );
  const shouldPoll = hasProcessing || awaitingSummary;
  useEffect(() => {
    if (!shouldPoll) return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const fresh = await api.listDocuments();
        if (alive) setDocs(fresh);
      } catch {
        /* transient — keep polling */
      }
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [shouldPoll]);

  // Выбор и открытая панель не должны переживать исчезновение документов.
  useEffect(() => {
    if (!docs) return;
    setChecked((cur) => {
      const next = new Set([...cur].filter((id) => docs.some((d) => d.id === id)));
      return next.size === cur.size ? cur : next;
    });
    setOpenId((cur) => (cur && !docs.some((d) => d.id === cur) ? null : cur));
  }, [docs]);

  // E20: «Открыть» на карточке готового документа в чате — раздел открылся
  // с запрошенной читалкой; id одноразовый, сбрасывается сразу после
  // применения (даже если документа уже нет — просто показываем список).
  const readerRequest = chatState.filesReaderDocId;
  useEffect(() => {
    if (!readerRequest || !docs) return;
    if (docs.some((d) => d.id === readerRequest)) setOpenId(readerRequest);
    clearFileReader();
  }, [readerRequest, docs, clearFileReader]);

  // Ошибки загрузки/вопроса не висят бессрочно.
  useEffect(() => {
    if (!uploadError && !askError) return;
    const timer = setTimeout(() => {
      setUploadError(null);
      setAskError(null);
    }, 8000);
    return () => clearTimeout(timer);
  }, [uploadError, askError]);

  // Панель монтируется закрытой и открывается следующим кадром — так CSS-переход
  // отыгрывает слайд; закрытие ждёт анимацию перед размонтированием.
  useEffect(() => {
    if (!openId) return;
    const raf = requestAnimationFrame(() => setPanelShown(true));
    return () => cancelAnimationFrame(raf);
  }, [openId]);
  useEffect(
    () => () => {
      if (closeTimer.current) clearTimeout(closeTimer.current);
    },
    [],
  );

  const closePanel = () => {
    setPanelShown(false);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpenId(null), PANEL_CLOSE_MS);
  };

  // Открытие поверх идущего закрытия (клик по другой строке) отменяет таймер;
  // повторный клик по открытой строке закрывает панель.
  const togglePanel = (id: string) => {
    if (openId === id && panelShown) {
      closePanel();
      return;
    }
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setOpenId(id);
    requestAnimationFrame(() => setPanelShown(true));
  };

  // Escape и клик за пределами панели закрывают её; пока открыт диалог
  // удаления (портал вне панели), внешние клики не считаются.
  useEffect(() => {
    if (!openId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel();
    };
    const onDown = (e: MouseEvent) => {
      if (pendingDelete) return;
      // клики по строке таблицы или карточке плитки сами управляют панелью
      // (togglePanel) — I2 (финальное ревью): один и тот же whitelist для
      // обоих видов, иначе в плитке «···» закрывает читалку, а повторный
      // клик по открытой карточке — не закрывает.
      if ((e.target as Element).closest?.(".files-row, .file-card")) return;
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) closePanel();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
    // closePanel намеренно не в зависимостях: стабильный по содержимому
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, pendingDelete]);

  const visible = useMemo(() => filterDocuments(docs ?? [], query), [docs, query]);
  const openDoc = docs?.find((d) => d.id === openId) ?? null;
  const askMode = checked.size > 0;

  const toggleCheck = (d: HubDocumentInfo) => {
    if (d.status !== "ready") return;
    setChecked((cur) => {
      const next = new Set(cur);
      if (next.has(d.id)) next.delete(d.id);
      else next.add(d.id);
      return next;
    });
  };

  const submitAsk = async () => {
    const text = question.trim();
    if (!text || asking || checked.size === 0) return;
    setAsking(true);
    setAskError(null);
    try {
      await askAboutDocuments([...checked], text);
    } catch {
      setAskError("Не удалось отправить вопрос. Попробуйте ещё раз.");
      setAsking(false);
      return;
    }
    setAsking(false);
    setQuestion("");
    setChecked(new Set());
  };

  const upload = async (file: File) => {
    const problem = validate(file);
    if (problem) {
      setUploadError(problem);
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      const created = await api.uploadLibraryDocument(file);
      setDocs((prev) => [created, ...(prev ?? []).filter((d) => d.id !== created.id)]);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Не удалось загрузить файл");
    } finally {
      setUploading(false);
    }
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void upload(file);
    e.target.value = "";
  };

  // dnd живёт на всём экране «Файлы»: drop мимо окна не должен уводить
  // браузер из приложения на локальный файл.
  const dragProps = {
    onDragEnter: (e: React.DragEvent) => {
      e.preventDefault();
      dragDepth.current += 1;
      setDragging(true);
    },
    onDragOver: (e: React.DragEvent) => e.preventDefault(),
    onDragLeave: () => {
      dragDepth.current -= 1;
      if (dragDepth.current <= 0) {
        dragDepth.current = 0;
        setDragging(false);
      }
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void upload(file);
    },
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.deleteDocument(pendingDelete.id);
      setDocs((prev) => (prev ?? []).filter((d) => d.id !== pendingDelete.id));
      setPendingDelete(null);
      if (openId === pendingDelete.id) {
        setPanelShown(false);
        setOpenId(null);
      }
    } catch {
      setDeleteError("Не удалось удалить документ");
    } finally {
      setDeleteBusy(false);
    }
  };

  const changeView = (mode: FilesViewMode) => {
    setViewMode(mode);
    saveViewMode(mode);
  };

  const docMenu = (d: HubDocumentInfo) => (
    <DocMenu
      doc={d}
      downloadUrl={api.documentDownloadUrl(d.id)}
      onOpen={() => togglePanel(d.id)}
      onAsk={() => {
        setChecked(new Set([d.id]));
        // Minor 9 (финальное ревью): полоса переключилась в режим вопроса —
        // сразу в поле, без лишнего клика. rAF ждёт коммит рендера, где
        // появляется сам input (тот же паттерн, что открытие панели ниже).
        requestAnimationFrame(() => stripInputRef.current?.focus());
      }}
      onReview={() => openReviewFor(d.id)}
      onDelete={() => {
        setDeleteError(null);
        setPendingDelete(d);
      }}
    />
  );

  const strip = (
    <>
      <div className={askMode ? "files-ask files-ask-on" : "files-ask"}>
        {askMode ? <MessageCircle size={15} /> : <Search size={15} />}
        <input
          ref={stripInputRef}
          value={askMode ? question : query}
          placeholder={
            askMode
              ? `Спросить по ${checked.size} выбранн${checked.size === 1 ? "ому документу" : "ым документам"}…`
              : "Поиск по документам…"
          }
          aria-label={askMode ? "Вопрос по выбранным документам" : "Поиск по документам"}
          onChange={(e) => (askMode ? setQuestion(e.target.value) : setQuery(e.target.value))}
          onKeyDown={(e) => {
            if (askMode && e.key === "Enter") void submitAsk();
          }}
        />
        {askMode && (
          <IconButton
            className="send"
            view="primary"
            icon={<ArrowUp size={18} />}
            disabled={asking || !question.trim()}
            onClick={() => void submitAsk()}
            aria-label="Отправить вопрос"
          />
        )}
      </div>
      {(askError ?? uploadError) && (
        <div className="files-strip-note">{askError ?? uploadError}</div>
      )}
    </>
  );

  return (
    <main className="files" {...dragProps}>
      <div className={dragging ? "files-win files-drag" : "files-win"}>
        <div className="files-bar">
          <span className="files-title">Файлы</span>
          {docs && <span className="files-count">{docs.length}</span>}
          <span className="files-bar-sp" />
          <div className="files-seg" role="group" aria-label="Вид отображения">
            <button
              type="button"
              className={viewMode === "list" ? "files-seg-on" : undefined}
              aria-label="Список"
              aria-pressed={viewMode === "list"}
              onClick={() => changeView("list")}
            >
              <List size={14} />
            </button>
            <button
              type="button"
              className={viewMode === "grid" ? "files-seg-on" : undefined}
              aria-label="Плитка"
              aria-pressed={viewMode === "grid"}
              onClick={() => changeView("grid")}
            >
              <LayoutGrid size={14} />
            </button>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".docx,.pdf"
            className="files-input"
            onChange={onPick}
          />
          <button
            type="button"
            className="files-btn"
            onClick={() => inputRef.current?.click()}
            disabled={docs === null || error || uploading}
          >
            <Upload size={13} /> {uploading ? "Загрузка…" : "Загрузить"}
          </button>
        </div>

        {error ? (
          <div className="src-state">
            Не удалось загрузить документы.
            <br />
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        ) : docs === null ? (
          <div className="files-table">
            <div className="src-skel" />
            <div className="src-skel" />
            <div className="src-skel" />
          </div>
        ) : docs.length === 0 ? (
          <div className="files-empty">
            {uploadError && <div className="files-strip-note">{uploadError}</div>}
            <div className="files-empty-icon">
              <Upload size={22} />
            </div>
            <div className="files-empty-title">Перетащите файл или загрузите</div>
            <div className="files-empty-text">Поддерживаются .docx и .pdf, до 20 МБ.</div>
          </div>
        ) : (
          <>
            {strip}
            {viewMode === "grid" ? (
              <div className="files-grid">
                {uploading && <div className="file-card file-card-skel" aria-hidden="true" />}
                {visible.length === 0 && !uploading && (
                  <div className="files-tnote">Ничего не найдено</div>
                )}
                {visible.map((d) => (
                  <FileCard
                    key={d.id}
                    doc={d}
                    checked={checked.has(d.id)}
                    onOpen={() => togglePanel(d.id)}
                    onToggleCheck={() => toggleCheck(d)}
                    menu={docMenu(d)}
                  />
                ))}
              </div>
            ) : (
              <div className="files-table">
                <div className="files-thead">
                  <span />
                  <span>Документ</span>
                  <span>Суть</span>
                  <span>Статус</span>
                  <span>Размер</span>
                  <span>Загружен</span>
                  <span />
                </div>
                {uploading && <div className="src-skel" />}
                {visible.length === 0 && !uploading && (
                  <div className="files-tnote">Ничего не найдено</div>
                )}
                {visible.map((d) => (
                  <div
                    key={d.id}
                    className={checked.has(d.id) ? "files-row files-row-on" : "files-row"}
                    role="button"
                    tabIndex={0}
                    onClick={() => togglePanel(d.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        togglePanel(d.id);
                      }
                    }}
                  >
                    <span
                      role="checkbox"
                      aria-checked={checked.has(d.id)}
                      aria-label={`Выбрать «${d.filename}»`}
                      aria-disabled={d.status !== "ready"}
                      tabIndex={d.status === "ready" ? 0 : -1}
                      className={
                        d.status !== "ready"
                          ? "files-check files-check-off"
                          : checked.has(d.id)
                            ? "files-check files-check-on"
                            : "files-check"
                      }
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleCheck(d);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          e.stopPropagation();
                          toggleCheck(d);
                        }
                      }}
                    />
                    <span className="files-doccell">
                      <FileTypeIcon parser={d.parser} />
                      <span className="files-name" title={d.filename}>
                        {d.filename}
                      </span>
                    </span>
                    <span
                      className={d.status === "ready" ? "files-sum" : "files-sum files-sum-note"}
                      title={d.status === "failed" ? humanizeDocError(d.error) : undefined}
                    >
                      {summaryLabel(d)}
                    </span>
                    <span><StatusPill status={d.status} /></span>
                    <span className="files-cell files-cell-size">{formatSize(d.size)}</span>
                    <span className="files-cell">{formatDate(d.created_at)}</span>
                    {docMenu(d)}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {openDoc && (
          <aside
            ref={panelRef}
            className={panelShown ? "files-panel files-panel-open" : "files-panel"}
          >
            <FilesReader
              key={openDoc.id}
              document={openDoc}
              onClose={closePanel}
              onDelete={() => {
                setDeleteError(null);
                setPendingDelete(openDoc);
              }}
            />
          </aside>
        )}
        {dragging && <div className="files-drag-note">Отпустите, чтобы загрузить</div>}
      </div>
      {pendingDelete && (
        <DeleteDialog
          document={pendingDelete}
          busy={deleteBusy}
          error={deleteError}
          onCancel={() => setPendingDelete(null)}
          onConfirm={confirmDelete}
        />
      )}
    </main>
  );
}
