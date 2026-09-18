import type { ReviewReport, ReviewRisk } from "../api/types";
import { LEVEL_LABELS, LEVEL_ORDER } from "../components/review/levels";

/** «Основание: ст. N АКТ, …» — из цитат риска; если корпус не дал основания
 * (no_basis, либо цитат нет вовсе), текст-заглушка. */
function basisText(risk: ReviewRisk): string {
  if (risk.no_basis || risk.citations.length === 0) return "норма в корпусе не найдена";
  return risk.citations.map((c) => `ст. ${c.number} ${c.act_short_name}`).join(", ");
}

function riskBlock(risk: ReviewRisk, isMissing: boolean): string {
  const level = LEVEL_LABELS[risk.level].toUpperCase();
  // §6 спеки: пункт печатается всегда, когда section_number есть (в т.ч. для
  // verdict=overstated) — «— возможно завышен» лишь добавляется следом, не
  // заменяет ссылку на пункт. Missing-правила остаются исключением: раздел в
  // договоре не найден, поэтому пункта у них нет вовсе.
  let suffix = "";
  if (isMissing) {
    suffix = " — раздел в договоре не найден";
  } else {
    if (risk.section_number) suffix += ` (п. ${risk.section_number})`;
    if (risk.verdict === "overstated") suffix += " — возможно завышен";
  }

  const lines = [`${level} · ${risk.title}${suffix}`];
  if (!isMissing && risk.contract_quote) lines.push(`Цитата: «${risk.contract_quote}»`);
  if (risk.explanation) lines.push(`Риск: ${risk.explanation}`);
  if (risk.recommendation) lines.push(`Рекомендация: ${risk.recommendation}`);
  lines.push(`Основание: ${basisText(risk)}`);
  return lines.join("\n");
}

/** Полный текст отчёта в утверждённом формате (§6 спеки T-0010) — для
 * «Копировать отчёт». `filename`/`when` — контекст шапки (документ и время),
 * оба необязательны и просто опускаются из «Документ: …», если не заданы. */
export function buildReviewReportText(
  report: ReviewReport,
  opts: { filename?: string; when?: string } = {},
): string {
  const { filename, when } = opts;

  const missingRuleIds = new Set(
    report.coverage.filter((c) => c.status === "missing").map((c) => c.rule_id),
  );
  const ordered = LEVEL_ORDER.flatMap((level) => report.risks.filter((r) => r.level === level));
  const high = report.risks.filter((r) => r.level === "high").length;
  const medium = report.risks.filter((r) => r.level === "medium").length;
  const low = report.risks.filter((r) => r.level === "low").length;

  const docParts = [filename, when].filter((x): x is string => Boolean(x));
  const headerBlock = [
    `Проверка договора: ${report.playbook_name}`,
    docParts.length > 0 ? `Документ: ${docParts.join(" · ")}` : null,
  ]
    .filter((line): line is string => line !== null)
    .join("\n");

  const sections: string[] = [headerBlock];

  if (report.summary) sections.push(`Итог: ${report.summary}`);

  sections.push(
    `Рисков: высокий ${high} · средний ${medium} · низкий ${low}. Проверено ${report.coverage.length} правил.`,
  );

  for (const risk of ordered) {
    sections.push(riskBlock(risk, missingRuleIds.has(risk.rule_id)));
  }

  const ok = report.coverage.filter((c) => c.status === "ok");
  const notApplicable = report.coverage.filter((c) => c.status === "not_applicable");
  const tailLines: string[] = [];
  if (ok.length > 0) {
    tailLines.push(`Остальные правила (${ok.length}): без замечаний — ${ok.map((c) => c.title).join(", ")}.`);
  }
  if (notApplicable.length > 0) {
    tailLines.push(`Неприменимо: ${notApplicable.map((c) => c.title).join(", ")}.`);
  }
  if (tailLines.length > 0) sections.push(tailLines.join("\n"));

  sections.push(
    when ? `${report.disclaimer}\nСформировано в Нейроюристе · ${when}` : `${report.disclaimer}\nСформировано в Нейроюристе`,
  );

  return sections.join("\n\n");
}

/** Текст одного риска для «Копировать риск» (замена riskCopyText,
 * T-0010/Задача 5): заголовок с разделом, риск, рекомендация, основание. */
export function buildRiskText(risk: ReviewRisk): string {
  const header = risk.title + (risk.section_number ? ` (п. ${risk.section_number})` : "");
  return [
    header,
    risk.explanation ? `Риск: ${risk.explanation}` : "",
    risk.recommendation ? `Рекомендация: ${risk.recommendation}` : "",
    `Основание: ${basisText(risk)}`,
  ]
    .filter(Boolean)
    .join("\n\n");
}
