import { describe, expect, it } from "vitest";
import { buildReviewReportText, buildRiskText } from "../util/reviewExport";
import type { Citation, ReviewCoverageItem, ReviewReport, ReviewRisk } from "../api/types";

function citation(over: Partial<Citation> = {}): Citation {
  return {
    act_short_name: "ГК РФ",
    kind: "codex",
    number: "1",
    title: null,
    full_text: "текст статьи",
    score: 0.5,
    ...over,
  };
}

function risk(over: Partial<ReviewRisk> = {}): ReviewRisk {
  return {
    citations: [],
    contract_quote: "",
    explanation: "",
    level: "medium",
    no_basis: false,
    recommendation: "",
    rule_id: "r1",
    section_number: null,
    title: "Риск",
    verdict: "confirmed",
    ...over,
  };
}

function coverage(over: Partial<ReviewCoverageItem> = {}): ReviewCoverageItem {
  return { rule_id: "c1", status: "ok", title: "Правило", ...over };
}

function report(over: Partial<ReviewReport> = {}): ReviewReport {
  return {
    coverage: [],
    disclaimer: "Черновая проверка: выводы требуют подтверждения юриста.",
    document_id: "d1",
    playbook_id: "supply_ru",
    playbook_name: "Договор поставки",
    risks: [],
    ...over,
  };
}

describe("buildReviewReportText", () => {
  it("полный отчёт (§6 спеки): 3 риска high/medium/missing-low, coverage ok×2 + not_applicable×1", () => {
    const medium = risk({
      rule_id: "r-medium",
      level: "medium",
      title: "Цена и порядок оплаты",
      section_number: "4.1",
      contract_quote: "Оплата производится в течение 10 банковских дней с даты поставки",
      explanation:
        "Порядок и момент оплаты сформулированы неоднозначно — неясно, с какого события считать срок.",
      recommendation:
        "Указать точную дату начала течения срока оплаты, например «с даты подписания товарной накладной».",
      citations: [citation({ number: "424" })],
    });
    const high = risk({
      rule_id: "r-high",
      level: "high",
      title: "Неустойка за просрочку",
      section_number: "6.2",
      contract_quote:
        "Поставщик уплачивает Покупателю неустойку в размере 0,5% от стоимости товара за каждый день просрочки без ограничения общей суммы.",
      explanation:
        "Неустойка не ограничена по сумме — при длительной просрочке она может превысить стоимость самой партии.",
      recommendation:
        "Ограничить общий размер неустойки, например: «но не более 10% от стоимости несвоевременно поставленного товара».",
      citations: [citation({ number: "330" }), citation({ number: "333" })],
    });
    const missing = risk({
      rule_id: "r-missing",
      level: "low",
      title: "Претензии и подсудность",
      section_number: null,
      contract_quote: "",
      explanation: "Правило ожидает раздел о претензионном порядке, но в договоре его нет.",
      recommendation: "Добавить раздел о порядке предъявления претензий и подсудности.",
      no_basis: true,
    });

    const r = report({
      risks: [medium, high, missing],
      coverage: [
        coverage({ rule_id: "r-medium", status: "risk", title: "Цена и порядок оплаты" }),
        coverage({ rule_id: "r-high", status: "risk", title: "Неустойка за просрочку" }),
        coverage({ rule_id: "r-missing", status: "missing", title: "Претензии и подсудность" }),
        coverage({ rule_id: "c-ok-1", status: "ok", title: "Наименование и количество товара" }),
        coverage({ rule_id: "c-ok-2", status: "ok", title: "Качество и гарантия" }),
        coverage({ rule_id: "c-na-1", status: "not_applicable", title: "Форс-мажор" }),
      ],
    });

    const text = buildReviewReportText(r, {
      filename: "договор_поставки.pdf",
      when: "18.07.26 14:32",
    });

    expect(text).toBe(
      [
        "Проверка договора: Договор поставки",
        "Документ: договор_поставки.pdf · 18.07.26 14:32",
        "",
        "Рисков: высокий 1 · средний 1 · низкий 1. Проверено 6 правил.",
        "",
        "ВЫСОКИЙ · Неустойка за просрочку (п. 6.2)",
        "Цитата: «Поставщик уплачивает Покупателю неустойку в размере 0,5% от стоимости товара за каждый день просрочки без ограничения общей суммы.»",
        "Риск: Неустойка не ограничена по сумме — при длительной просрочке она может превысить стоимость самой партии.",
        "Рекомендация: Ограничить общий размер неустойки, например: «но не более 10% от стоимости несвоевременно поставленного товара».",
        "Основание: ст. 330 ГК РФ, ст. 333 ГК РФ",
        "",
        "СРЕДНИЙ · Цена и порядок оплаты (п. 4.1)",
        "Цитата: «Оплата производится в течение 10 банковских дней с даты поставки»",
        "Риск: Порядок и момент оплаты сформулированы неоднозначно — неясно, с какого события считать срок.",
        "Рекомендация: Указать точную дату начала течения срока оплаты, например «с даты подписания товарной накладной».",
        "Основание: ст. 424 ГК РФ",
        "",
        "НИЗКИЙ · Претензии и подсудность — раздел в договоре не найден",
        "Риск: Правило ожидает раздел о претензионном порядке, но в договоре его нет.",
        "Рекомендация: Добавить раздел о порядке предъявления претензий и подсудности.",
        "Основание: норма в корпусе не найдена",
        "",
        "Остальные правила (2): без замечаний — Наименование и количество товара, Качество и гарантия.",
        "Неприменимо: Форс-мажор.",
        "",
        "Черновая проверка: выводы требуют подтверждения юриста.",
        "Сформировано в Нейроюристе · 18.07.26 14:32",
      ].join("\n"),
    );
  });

  it("verdict=overstated печатает «(п. X.Y)» и добавляет суффикс «— возможно завышен» следом", () => {
    const r = report({
      risks: [
        risk({
          rule_id: "r1",
          level: "high",
          title: "Односторонний отказ",
          section_number: "9.1",
          verdict: "overstated",
          explanation: "x",
        }),
      ],
      coverage: [coverage({ rule_id: "r1", status: "risk", title: "Односторонний отказ" })],
    });
    const text = buildReviewReportText(r, {});
    expect(text).toContain("ВЫСОКИЙ · Односторонний отказ (п. 9.1) — возможно завышен");
  });

  it("verdict=overstated без section_number — только суффикс, без «(п. …)»", () => {
    const r = report({
      risks: [
        risk({
          rule_id: "r1",
          level: "high",
          title: "Без раздела",
          section_number: null,
          verdict: "overstated",
          explanation: "x",
        }),
      ],
      coverage: [coverage({ rule_id: "r1", status: "risk", title: "Без раздела" })],
    });
    const text = buildReviewReportText(r, {});
    expect(text).toContain("ВЫСОКИЙ · Без раздела — возможно завышен");
    expect(text).not.toContain("(п.");
  });

  it("без filename/when — «Документ:» и «Сформировано» опускают контекст", () => {
    const r = report({ risks: [], coverage: [] });
    const text = buildReviewReportText(r, {});
    expect(text).toBe(
      [
        "Проверка договора: Договор поставки",
        "Рисков: высокий 0 · средний 0 · низкий 0. Проверено 0 правил.",
        "Черновая проверка: выводы требуют подтверждения юриста.\nСформировано в Нейроюристе",
      ].join("\n\n"),
    );
  });

  it("summary непустой — добавляет строку «Итог: …» (когда контракт его отдаёт)", () => {
    const withSummary = { ...report({ risks: [], coverage: [] }), summary: "Договор в целом рабочий." };
    const text = buildReviewReportText(withSummary, {});
    expect(text).toContain("Итог: Договор в целом рабочий.");
  });

  it("summary отсутствует — строки «Итог:» нет", () => {
    const text = buildReviewReportText(report({ risks: [], coverage: [] }), {});
    expect(text).not.toContain("Итог:");
  });
});

describe("buildRiskText", () => {
  it("заголовок с разделом + Риск/Рекомендация/Основание, без служебных полей", () => {
    const r = risk({
      rule_id: "r1",
      title: "Односторонний отказ",
      section_number: "1",
      explanation: "Условие ущемляет покупателя",
      recommendation: "Согласовать порядок отказа",
    });
    expect(buildRiskText(r)).toBe(
      [
        "Односторонний отказ (п. 1)",
        "Риск: Условие ущемляет покупателя",
        "Рекомендация: Согласовать порядок отказа",
        "Основание: норма в корпусе не найдена",
      ].join("\n\n"),
    );
  });

  it("без section_number — заголовок без «(п. …)»", () => {
    const r = risk({ title: "Риск без раздела", section_number: null, explanation: "x" });
    expect(buildRiskText(r)).toContain("Риск без раздела\n\n");
    expect(buildRiskText(r)).not.toContain("(п.");
  });

  it("с цитатами — «Основание: ст. N АКТ, …»", () => {
    const r = risk({
      title: "С основанием",
      citations: [citation({ number: "330" }), citation({ number: "333" })],
    });
    expect(buildRiskText(r)).toContain("Основание: ст. 330 ГК РФ, ст. 333 ГК РФ");
  });

  it("no_basis — «Основание: норма в корпусе не найдена»", () => {
    const r = risk({
      title: "Без основания",
      no_basis: true,
      citations: [citation({ number: "330" })],
    });
    expect(buildRiskText(r)).toContain("Основание: норма в корпусе не найдена");
  });
});
