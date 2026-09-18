import { Plus, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../../api/client";
import type { HubDocumentInfo, Message, ReviewListItem, ReviewsResponse } from "../../api/types";
import { useChat } from "../../state/ChatContext";
import { FileTypeIcon } from "../files/FileTypeIcon";
import { formatDate } from "../files/format";
import { ReviewPanel } from "../review/ReviewPanel";
import { LEVEL_LABELS, LevelDot } from "../review/levels";
import { NewReviewDialog, type NewReviewStart } from "./NewReviewDialog";
import { filterReviews } from "./filter";

const PANEL_CLOSE_MS = 240;

/** Панель отчёта берёт HubDocumentInfo, но раздел знает о документе только
 * имя/тип из строки свода — синтезируем минимальный объект для DocChip
 * (он читает одно поле filename). */
function rowDoc(item: ReviewListItem): HubDocumentInfo | null {
  if (!item.document_filename) return null;
  return {
    id: item.document_id,
    owner_id: "",
    filename: item.document_filename,
    content_type: "",
    size: 0,
    status: "ready",
    parser: item.document_parser ?? "docx",
    created_at: item.created_at,
  };
}

function Counts({ item }: { item: ReviewListItem }) {
  const levels = [
    { level: "high" as const, n: item.high },
    { level: "medium" as const, n: item.medium },
    { level: "low" as const, n: item.low },
  ].filter((l) => l.n > 0);
  if (levels.length === 0) return <span className="rvs-cell-note">0 рисков</span>;
  return (
    <span className="rvs-counts">
      {levels.map((l) => (
        <span key={l.level} className="rvs-lvl">
          <LevelDot level={l.level} />
          <span className="visually-hidden">{LEVEL_LABELS[l.level]}: </span>
          {l.n}
        </span>
      ))}
    </span>
  );
}

/** Ярлык review-хода несёт имя файла и плейбука («Проверить «X»: Y» — тот же
 * формат, что чип документа в чате); разбор — только для отображения живой
 * строки, при несовпадении формата ярлык уходит в колонку плейбука целиком. */
function parseRunLabel(label: string): { filename: string | null; playbookName: string } {
  const m = label.match(/^Проверить «(.+)»: (.+)$/);
  return m ? { filename: m[1], playbookName: m[2] } : { filename: null, playbookName: label };
}

/** Раздел «Проверки» (T-0048): окно в языке «Файлов» — bar, поиск, таблица
 * прогонов; клик по строке открывает ту же панель отчёта, что и чат. */
export function ReviewsView() {
  const { state, openConversation, prefillComposer, startReviewFromSection, clearReviewRequest } =
    useChat();
  const [data, setData] = useState<ReviewsResponse | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<{ item: ReviewListItem; message: Message } | null>(null);
  const [panelShown, setPanelShown] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogDocId, setDialogDocId] = useState<string | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panelRef = useRef<HTMLElement>(null);

  // T-0148: пришли из «Файлов» по «Проверить на риски» — открываем диалог
  // с этим документом; запрос одноразовый.
  const reviewRequest = state.reviewRequestDocId;
  useEffect(() => {
    if (!reviewRequest) return;
    setDialogDocId(reviewRequest);
    setDialogOpen(true);
    clearReviewRequest();
  }, [reviewRequest, clearReviewRequest]);

  const load = () => {
    setError(false);
    setData(null);
    api.listReviews().then(setData).catch(() => setError(true));
  };
  useEffect(load, []);

  // Живой прогресс — только прогон текущей сессии (спека §2): review-ход,
  // чей turnId совпадает с активным стримом. По завершении (falling edge)
  // список перечитывается — синтетическая строка сменяется серверной
  // (done или failed).
  const liveRun =
    state.streaming && state.lastReviewRequest && state.lastReviewRequest.turnId === state.turnId
      ? state.lastReviewRequest
      : null;
  const wasLive = useRef(false);
  useEffect(() => {
    if (liveRun) {
      wasLive.current = true;
      return;
    }
    if (wasLive.current) {
      wasLive.current = false;
      load();
    }
  }, [liveRun]);

  // Панель монтируется закрытой и открывается следующим кадром (слайд как в
  // FilesView); закрытие ждёт анимацию перед размонтированием.
  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => setPanelShown(true));
    return () => cancelAnimationFrame(raf);
  }, [open]);
  useEffect(
    () => () => {
      if (closeTimer.current) clearTimeout(closeTimer.current);
    },
    [],
  );

  const closePanel = () => {
    setPanelShown(false);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpen(null), PANEL_CLOSE_MS);
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if ((e.target as Element).closest?.(".rvs-row")) return;
      // Меню «Скачать» панели рендерится порталом на body (core-ds Popover) —
      // физически вне panelRef; без guard'а клик по «Скачать DOCX»/«Сохранить
      // в PDF» закрывал панель прямо во время действия (T-0052).
      if ((e.target as Element).closest?.(".rvp-dl-menu")) return;
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) closePanel();
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
    // closePanel стабильный по содержимому
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const openRow = async (item: ReviewListItem) => {
    if (item.status !== "done") return;
    if (open?.item.message_id === item.message_id && panelShown) {
      closePanel();
      return;
    }
    setOpenError(null);
    try {
      const messages = await api.getMessages(item.conversation_id);
      const message = messages.find((m) => m.id === item.message_id);
      if (!message?.review) throw new Error("report missing");
      if (closeTimer.current) {
        clearTimeout(closeTimer.current);
        closeTimer.current = null;
      }
      setOpen({ item, message });
      requestAnimationFrame(() => setPanelShown(true));
    } catch {
      setOpenError("Не удалось открыть отчёт. Попробуйте ещё раз.");
    }
  };

  // «Обсудить» из панели раздела: сперва открыть беседу прогона (переключает
  // view на чат), затем префиллить композер той же затравкой, что и в чате.
  const discuss = (item: ReviewListItem) => (prefill: string) => {
    void openConversation(item.conversation_id).then(() => prefillComposer(prefill));
  };

  const visible = useMemo(() => filterReviews(data?.items ?? [], query), [data, query]);

  return (
    <main className="files rvs">
      <div className="files-win">
        <div className="files-bar">
          <span className="files-title">Проверки</span>
          {data && <span className="files-count">{data.total}</span>}
          <span className="files-bar-sp" />
          <button
            type="button"
            className="files-btn"
            onClick={() => setDialogOpen(true)}
            disabled={error || liveRun !== null}
          >
            <Plus size={13} /> Новая проверка
          </button>
        </div>
        {openError && <div className="files-strip-note">{openError}</div>}

        {error ? (
          <div className="src-state">
            Не удалось загрузить проверки.
            <br />
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        ) : data === null ? (
          <div className="files-table">
            <div className="src-skel" />
            <div className="src-skel" />
            <div className="src-skel" />
          </div>
        ) : data.items.length === 0 && !liveRun ? (
          <div className="files-empty">
            <div className="files-empty-icon">
              <Search size={22} />
            </div>
            <div className="files-empty-title">Проверок ещё не было</div>
            <div className="files-empty-text">
              Запустите первую: «Новая проверка» или скрепка в чате.
            </div>
          </div>
        ) : (
          <>
            <div className="files-ask">
              <Search size={15} />
              <input
                value={query}
                placeholder="Найти проверку — по документу или плейбуку"
                aria-label="Поиск по проверкам"
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="files-table">
              <div className="rvs-thead">
                <span>Плейбук</span>
                <span>Документ</span>
                <span>Риски</span>
                <span>Когда</span>
              </div>
              {liveRun &&
                (() => {
                  const { filename, playbookName } = parseRunLabel(liveRun.label);
                  return (
                    <div className="rvs-row rvs-row-live" aria-disabled>
                      <span className="rvs-pb">
                        {playbookName}
                        <small>{liveRun.role ? `вы — ${liveRun.role}` : "роль не указана"}</small>
                      </span>
                      <span className="rvs-doccell">
                        {filename ? (
                          <>
                            <FileTypeIcon
                              parser={filename.toLowerCase().endsWith(".pdf") ? "pdf" : "docx"}
                            />
                            <span className="rvs-docname">{filename}</span>
                          </>
                        ) : (
                          <span className="rvs-cell-note">—</span>
                        )}
                      </span>
                      <span className="rvs-run">
                        {state.reviewProgress
                          ? `идёт · ${state.reviewProgress.index} из ${state.reviewProgress.total}`
                          : "идёт"}
                      </span>
                      <span className="rvs-date">сейчас</span>
                    </div>
                  );
                })()}
              {visible.length === 0 && !liveRun && (
                <div className="files-tnote">Ничего не найдено</div>
              )}
              {visible.map((item) => (
                <div
                  key={item.message_id}
                  className="rvs-row"
                  role="button"
                  tabIndex={0}
                  aria-disabled={item.status !== "done"}
                  onClick={() => void openRow(item)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void openRow(item);
                    }
                  }}
                >
                  <span className="rvs-pb">
                    {item.playbook_name}
                    <small>{item.role ? `вы — ${item.role}` : "роль не указана"}</small>
                  </span>
                  <span className="rvs-doccell">
                    {item.document_filename ? (
                      <>
                        <FileTypeIcon parser={item.document_parser ?? "docx"} />
                        <span className="rvs-docname" title={item.document_filename}>
                          {item.document_filename}
                        </span>
                      </>
                    ) : (
                      <span className="rvs-cell-note">документ удалён</span>
                    )}
                  </span>
                  {item.status === "failed" ? (
                    <span className="rvs-cell-note" title={item.error ?? undefined}>
                      проверка не удалась
                    </span>
                  ) : (
                    <Counts item={item} />
                  )}
                  <span className="rvs-date">{formatDate(item.created_at)}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {open && (
          <aside
            ref={panelRef}
            className={panelShown ? "files-panel files-panel-open" : "files-panel"}
          >
            <ReviewPanel
              key={open.message.id}
              message={open.message}
              doc={rowDoc(open.item)}
              onClose={closePanel}
              onDiscuss={discuss(open.item)}
            />
          </aside>
        )}
      </div>
      {dialogOpen && (
        <NewReviewDialog
          initialDocumentId={dialogDocId}
          onClose={() => {
            setDialogOpen(false);
            setDialogDocId(null);
          }}
          onStart={(args: NewReviewStart) => {
            setDialogOpen(false);
            setDialogDocId(null);
            setOpenError(null);
            // Сбой до старта стрима (attach упал: сеть/хаб) — единственная
            // точка, где прогон молча не начнётся; показываем строку ошибки.
            startReviewFromSection(
              args.documentId,
              args.playbookId,
              `Проверить «${args.filename}»: ${args.playbookName}`,
              args.role,
            ).catch(() => setOpenError("Не удалось запустить проверку. Попробуйте ещё раз."));
          }}
        />
      )}
    </main>
  );
}
