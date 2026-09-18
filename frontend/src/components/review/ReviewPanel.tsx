import { ChevronRight, Download, MessageSquare, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { HubDocumentInfo, Message, ReviewRisk } from "../../api/types";
import { reviewExportUrl } from "../../api/client";
import { useChat } from "../../state/ChatContext";
import { formatTimestamp } from "../../util/format";
import { buildReviewReportText, buildRiskText } from "../../util/reviewExport";
import { CitationChip } from "../CitationChip";
import { CitationsProvider } from "../CitationsContext";
import { CopyButton } from "../CopyButton";
import { IconButton, Popover, Tooltip } from "../../ui";
import { DocChip } from "./DocChip";
import { LEVEL_LABELS, LEVEL_ORDER, LevelDot } from "./levels";

function riskKey(risk: ReviewRisk, i: number): string {
  return `${risk.rule_id}-${i}`;
}

const OVERSTATED_TOOLTIP =
  "Проверка по нормам показала, что риск может быть преувеличен — прочитайте и оцените сами";
const MISSING_SECTION_TOOLTIP = "Правило ожидает раздел в договоре, но он не найден";

// Whether a risk is a "missing clause" risk comes from coverage (the engine
// records status "missing" for the rule), NOT from section_number == null:
// the backend hides sentinel section ids ("preamble", "trailing", "pN") via
// _public_section_number(), so an ordinary risk quoted from the preamble has
// section_number == null too — and a missing risk the model returned with a
// section number keeps it non-null.
function verdictBadge(risk: ReviewRisk, missingRuleIds: ReadonlySet<string>): {
  text: string;
  tooltip: string;
} | null {
  if (risk.verdict === "overstated") {
    return { text: "возможно завышен", tooltip: OVERSTATED_TOOLTIP };
  }
  if (missingRuleIds.has(risk.rule_id)) {
    return { text: "раздел не найден", tooltip: MISSING_SECTION_TOOLTIP };
  }
  return null;
}

const COVERAGE_OTHER_LABEL: Record<"ok" | "not_applicable", string> = {
  ok: "в порядке",
  not_applicable: "неприменимо к этому договору",
};

interface ReviewPanelProps {
  message: Message;
  /** T-0048: панель из раздела «Проверки» живёт вне беседы — документ
   * передаётся снаружи (undefined = искать в state.documents, как в чате;
   * null = документа нет). */
  doc?: HubDocumentInfo | null;
  /** Замена closeReviewPanel из контекста (раздел закрывает свой aside). */
  onClose?: () => void;
  /** Замена «префилл композера + закрыть панель»: раздел сперва открывает
   * беседу прогона, затем префиллит. Получает готовый текст затравки. */
  onDiscuss?: (prefill: string) => void;
}

/** Слайд-панель отчёта о рисках (T-0010) — рендерится поверх .chat-win рядом
 * с MessageList. Читает отчёт сама по переданному сообщению; ChatPane решает,
 * рендерить ли панель вовсе (по state.reviewPanelFor). */
export function ReviewPanel({ message, doc: docProp, onClose, onDiscuss }: ReviewPanelProps) {
  const { state, closeReviewPanel, prefillComposer } = useChat();
  const close = onClose ?? closeReviewPanel;
  const report = message.review ?? null;
  const panelRef = useRef<HTMLDivElement>(null);

  const ordered = useMemo(
    () => (report ? LEVEL_ORDER.flatMap((level) => report.risks.filter((r) => r.level === level)) : []),
    [report],
  );

  const [openKeys, setOpenKeys] = useState<Set<string>>(
    () => new Set(ordered.length > 0 ? [riskKey(ordered[0], 0)] : []),
  );

  // Вердикт-бейдж: тултип у @alfalab TooltipDesktop поддерживает только
  // trigger "click"/"hover" (нет "focus") — клавиатурный путь даём сами:
  // фокус на кнопке-строке (единственный tab-stop строки, канонический WAI
  // tooltip-on-focus) форсирует показ тултипа через controlled
  // `open={focusedVerdict === key || undefined}`; `undefined` в остальное
  // время отдаёт управление внутреннему hover-состоянию тултипа. Для
  // скрин-ридеров текст пояснения продублирован скрытым span'ом и привязан
  // к строке как ОПИСАНИЕ (aria-describedby), не имя — accessible name
  // строки остаётся коротким.
  const [focusedVerdict, setFocusedVerdict] = useState<string | null>(null);

  // Меню «Скачать» (T-0049) — паттерн клика-вне как в SourceSelector.
  const [dlOpen, setDlOpen] = useState(false);
  const [dlAnchor, setDlAnchor] = useState<HTMLElement | null>(null);
  const dlMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!dlOpen) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (dlAnchor?.contains(t) || dlMenuRef.current?.contains(t)) return;
      setDlOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [dlOpen, dlAnchor]);

  const [printing, setPrinting] = useState(false);

  // Печать в PDF (T-0049): print-режим раскрывает все риски (сжатые тела
  // не в DOM — CSS их не раскроет), body.rvp-printing включает @media print
  // маску «только панель». rAF гарантирует, что раскрытые тела успели
  // отрендериться до print(); afterprint откатывает всё.
  useEffect(() => {
    if (!printing) return;
    document.body.classList.add("rvp-printing");
    const raf = requestAnimationFrame(() => window.print());
    const done = () => setPrinting(false);
    window.addEventListener("afterprint", done);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("afterprint", done);
      document.body.classList.remove("rvp-printing");
    };
  }, [printing]);

  // A newly-opened report (different message) starts fresh: only its first
  // risk expanded, regardless of what was open in a previously-viewed report.
  useEffect(() => {
    setOpenKeys(new Set(ordered.length > 0 ? [riskKey(ordered[0], 0)] : []));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message.id]);

  useEffect(() => {
    // preventScroll: обычный focus() скроллил контейнер чата к панели —
    // «экран дёргается назад» при открытии отчёта (T-0052).
    panelRef.current?.focus({ preventScroll: true });
  }, [message.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Scoping (T-0052): открытое меню «Скачать» закрывается первым,
      // панель — следующим Escape.
      if (dlOpen) {
        setDlOpen(false);
        return;
      }
      close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close, dlOpen]);

  if (!report) return null;

  const doc =
    docProp !== undefined ? (docProp ?? undefined) : state.documents.find((d) => d.id === report.document_id);
  const missingRuleIds = new Set(
    report.coverage.filter((c) => c.status === "missing").map((c) => c.rule_id),
  );
  const coverageOther = report.coverage.filter(
    (c): c is typeof c & { status: "ok" | "not_applicable" } =>
      c.status === "ok" || c.status === "not_applicable",
  );

  const toggle = (key: string) => {
    setOpenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // «Копировать отчёт» (шапка + низ панели, Задача 5): формат §6 спеки —
  // документ и время идут из этого же чипа/сообщения, тем же путём, что
  // читает шапка.
  const reportText = buildReviewReportText(report, {
    filename: doc?.filename,
    when: formatTimestamp(message.created_at),
  });

  // «Обсудить в чате» (Задача 5): кладёт затравку в композер и закрывает
  // панель — дальше пользователь просто дописывает вопрос и отправляет.
  // Из раздела «Проверки» (T-0048) вместо этого зовётся onDiscuss — разделу
  // сперва надо открыть беседу прогона.
  const discuss = (prefill: string) => {
    if (onDiscuss) {
      onDiscuss(prefill);
      return;
    }
    prefillComposer(prefill);
    closeReviewPanel();
  };

  const discussRisk = (risk: ReviewRisk) => {
    discuss(`Про риск «${risk.title}»${risk.section_number ? ` (п. ${risk.section_number})` : ""}: `);
  };

  const discussAllRisks = () => {
    discuss(`Про риски из проверки «${report.playbook_name}»: `);
  };

  return (
    <div
      // rvp-open: панель монтируется условно (нет отдельного закрытого
      // состояния), поэтому она всегда несёт модификатор геометрии
      // files-panel (см. review-panel.css) — статично «открыта», когда есть.
      className="rvp-panel rvp-open"
      role="dialog"
      aria-modal="false"
      aria-label={`Отчёт: ${report.playbook_name}`}
      tabIndex={-1}
      ref={panelRef}
    >
      <div className="rvp-head">
        <div className="rvp-titles">
          <div className="rvp-title">
            {report.playbook_name}
            <span className="rvp-time"> · {formatTimestamp(message.created_at)}</span>
          </div>
          <div className="rvp-sub">
            <DocChip doc={doc} />
            {report.role && <span>вы — {report.role}</span>}
          </div>
        </div>
        <span ref={setDlAnchor} className="rvp-head-dl">
          <IconButton
            icon={<Download size={16} />}
            onClick={() => setDlOpen((v) => !v)}
            aria-label="Скачать"
            aria-expanded={dlOpen}
          />
        </span>
        <Popover anchorElement={dlAnchor} open={dlOpen} position="bottom-end">
          <div className="rvp-dl-menu" ref={dlMenuRef}>
            <a
              className="rvp-dl-item"
              href={reviewExportUrl(message.id)}
              download
              onClick={() => setDlOpen(false)}
            >
              Скачать DOCX
            </a>
            <button
              type="button"
              className="rvp-dl-item"
              onClick={() => {
                setDlOpen(false);
                setPrinting(true);
              }}
            >
              Сохранить в PDF
            </button>
          </div>
        </Popover>
        <CopyButton text={reportText} label="Копировать отчёт" className="rvp-head-copy" />
        {/* Обёртка даёт печатному CSS стабильный класс-крючок — сам
            core-ds IconButton несёт только внутренний cc-icon-button
            (не публичный контракт компонента, менять не будем). */}
        <span className="rvp-head-close">
          <IconButton
            icon={<X size={16} />}
            onClick={close}
            aria-label="Закрыть"
          />
        </span>
      </div>

      <div className="rvp-body">
        {report.summary ? <p className="rvp-summary">{report.summary}</p> : null}

        {ordered.length > 0 && (
          <>
            <h2 className="rvp-sec-h">Риски</h2>
            {ordered.map((risk, i) => {
              const key = riskKey(risk, i);
              const isOpen = printing || openKeys.has(key);
              const badge = verdictBadge(risk, missingRuleIds);
              const noteId = `rvp-verdict-note-${key}`;
              return (
                <div key={key} className={isOpen ? "rvp-risk open" : "rvp-risk"}>
                  <button
                    type="button"
                    className="rvp-risk-row"
                    aria-expanded={isOpen}
                    aria-describedby={badge ? noteId : undefined}
                    onClick={() => toggle(key)}
                    onFocus={() => badge && setFocusedVerdict(key)}
                    onBlur={() =>
                      badge && setFocusedVerdict((prev) => (prev === key ? null : prev))
                    }
                  >
                    <span className="rvp-lvl rvp-lvl-tag">
                      <LevelDot level={risk.level} />
                      {LEVEL_LABELS[risk.level]}
                    </span>
                    <span className="rvp-risk-title">{risk.title}</span>
                    {badge && (
                      <Tooltip
                        content={badge.tooltip}
                        targetTag="span"
                        open={focusedVerdict === key || undefined}
                      >
                        <span className="rvp-verdict">{badge.text}</span>
                      </Tooltip>
                    )}
                    {/* section_number приходит сырым («6.2») — префикс «п.»
                        добавляет UI, как и текстовый экспорт (reviewExport). */}
                    <span className="rvp-risk-ref">
                      {risk.section_number ? `п. ${risk.section_number}` : "—"}
                    </span>
                    <ChevronRight size={14} className="rvp-chev" aria-hidden />
                  </button>
                  {/* Пояснение вердикта для SR — снаружи кнопки (иначе попало
                      бы в её name-from-contents), привязано aria-describedby. */}
                  {badge && (
                    <span id={noteId} className="visually-hidden">
                      {badge.tooltip}
                    </span>
                  )}
                  {isOpen && (
                    <div className="rvp-risk-body">
                      {risk.contract_quote && (
                        <blockquote className="rvp-quote">
                          {risk.section_number && (
                            <span className="rvp-quote-ref">п. {risk.section_number}</span>
                          )}
                          {risk.contract_quote}
                        </blockquote>
                      )}
                      {risk.explanation && <p className="rvp-risk-text">{risk.explanation}</p>}
                      {risk.recommendation && (
                        <div className="rvp-reco">
                          <div className="rvp-reco-label">Рекомендация</div>
                          <p>{risk.recommendation}</p>
                        </div>
                      )}
                      {risk.no_basis ? (
                        <p className="rvp-nobasis">норма в корпусе не найдена</p>
                      ) : (
                        risk.citations.length > 0 && (
                          <CitationsProvider value={risk.citations}>
                            <div className="rvp-cites">
                              {risk.citations.map((c) => (
                                <CitationChip
                                  key={`${c.act_short_name}-${c.number}`}
                                  dataAct={c.act_short_name}
                                  dataNumbers={c.number}
                                >
                                  ст. {c.number} {c.act_short_name}
                                </CitationChip>
                              ))}
                            </div>
                          </CitationsProvider>
                        )
                      )}
                      <div className="rvp-next">
                        <button
                          type="button"
                          className="rvp-quiet-btn"
                          onClick={() => discussRisk(risk)}
                        >
                          Обсудить в чате
                        </button>
                        <CopyButton text={buildRiskText(risk)} label="Копировать риск" />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </>
        )}

        {coverageOther.length > 0 && (
          <>
            <h2 className="rvp-sec-h">
              Остальные правила <small>{coverageOther.length} · замечаний нет</small>
            </h2>
            {coverageOther.map((c) => (
              <div key={c.rule_id} className="rvp-cov-row">
                <span className="rvp-cov-name">{c.title}</span>
                <span className={c.status === "ok" ? "rvp-cov-status rvp-cov-status-ok" : "rvp-cov-status"}>
                  {COVERAGE_OTHER_LABEL[c.status]}
                </span>
              </div>
            ))}
          </>
        )}

        <div className="rvp-actions">
          <button type="button" className="rvp-btn" onClick={discussAllRisks}>
            <MessageSquare size={14} />
            Обсудить риски в чате
          </button>
          <CopyButton text={reportText} label="Копировать отчёт" variant="text" />
        </div>

        <p className="rvp-disclaimer">{report.disclaimer}</p>
      </div>
    </div>
  );
}
