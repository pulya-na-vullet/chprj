import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";

import { ReviewPanel } from "../components/review/ReviewPanel";
import type {
  HubDocumentInfo,
  Message,
  ReviewCoverageItem,
  ReviewReport,
  ReviewRisk,
} from "../api/types";

const closeReviewPanel = vi.fn();
const prefillComposer = vi.fn();
const documents: HubDocumentInfo[] = [
  {
    id: "d1",
    owner_id: "default",
    filename: "договор_поставки.pdf",
    content_type: "application/pdf",
    size: 2048,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    summary: null,
    created_at: "2026-07-08T00:00:00Z",
  },
];

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({ state: { documents }, closeReviewPanel, prefillComposer }),
}));

function risk(over: Partial<ReviewRisk> = {}): ReviewRisk {
  return {
    citations: [],
    contract_quote: "",
    explanation: "",
    level: "medium",
    no_basis: false,
    recommendation: "",
    rule_id: "r1",
    // Сырое значение, как шлёт бэкенд (engine._public_section_number):
    // префикс «п.» добавляет UI/форматтер, не контракт.
    section_number: "1",
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

function message(over: Partial<Message> = {}): Message {
  return {
    id: "m1",
    role: "assistant",
    content: "",
    citations: null,
    stopped: false,
    created_at: "2026-07-18T14:32:00",
    review: report(),
    ...over,
  };
}

beforeEach(() => {
  closeReviewPanel.mockClear();
  prefillComposer.mockClear();
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
});

describe("ReviewPanel", () => {
  it("рендерит риски по уровням со словесными метками и порядком high→low", () => {
    const { container } = render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [
              risk({ rule_id: "low1", level: "low", title: "Низкий риск" }),
              risk({ rule_id: "high1", level: "high", title: "Высокий риск" }),
              risk({ rule_id: "med1", level: "medium", title: "Средний риск" }),
            ],
          }),
        })}
      />,
    );
    const rows = container.querySelectorAll(".rvp-risk-row");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Высокий");
    expect(rows[0]).toHaveTextContent("Высокий риск");
    expect(rows[1]).toHaveTextContent("Средний");
    expect(rows[1]).toHaveTextContent("Средний риск");
    expect(rows[2]).toHaveTextContent("Низкий");
    expect(rows[2]).toHaveTextContent("Низкий риск");
  });

  it("аккордеон: первый риск раскрыт по умолчанию, клик переключает aria-expanded и тело", () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [
              risk({ rule_id: "r1", title: "Первый", explanation: "Объяснение первого" }),
              risk({ rule_id: "r2", title: "Второй", explanation: "Объяснение второго" }),
            ],
          }),
        })}
      />,
    );
    const row1 = screen.getByRole("button", { name: /Первый/ });
    const row2 = screen.getByRole("button", { name: /Второй/ });
    expect(row1).toHaveAttribute("aria-expanded", "true");
    expect(row2).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Объяснение первого")).toBeInTheDocument();
    expect(screen.queryByText("Объяснение второго")).toBeNull();

    fireEvent.click(row2);
    expect(row2).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Объяснение второго")).toBeInTheDocument();

    fireEvent.click(row1);
    expect(row1).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Объяснение первого")).toBeNull();
  });

  it("ref-колонка и quote-ref рендерят «п. {section_number}» из сырого значения бэкенда", () => {
    const { container } = render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [
              risk({
                rule_id: "r1",
                title: "Неустойка",
                section_number: "6.2",
                contract_quote: "Неустойка 0,5% в день без ограничения.",
              }),
            ],
          }),
        })}
      />,
    );
    // Ref column in the (auto-expanded first) risk row.
    expect(container.querySelector(".rvp-risk-ref")).toHaveTextContent("п. 6.2");
    // Quote ref inside the expanded body — same prefix, no double "п. п.".
    expect(container.querySelector(".rvp-quote-ref")).toHaveTextContent(/^п\. 6\.2$/);
  });

  it("бейдж «раздел не найден» у missing-риска (по coverage); тултип-текст присутствует по наведению", async () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Без раздела", section_number: null })],
            coverage: [coverage({ rule_id: "r1", status: "missing", title: "Без раздела" })],
          }),
        })}
      />,
    );
    const badge = screen.getByText("раздел не найден");
    expect(badge).toBeInTheDocument();
    // Ref column shows "—" for a risk with no section.
    expect(screen.getByText("—")).toBeInTheDocument();
    // Текст пояснения всегда есть один раз (скрытый SR-span); по наведению
    // появляется второй экземпляр — видимый тултип.
    expect(screen.getAllByText("Правило ожидает раздел в договоре, но он не найден")).toHaveLength(1);
    fireEvent.mouseOver(badge);
    await waitFor(() =>
      expect(
        screen.getAllByText("Правило ожидает раздел в договоре, но он не найден"),
      ).toHaveLength(2),
    );
  });

  it("риск с section_number=null, но coverage-статусом risk — БЕЗ бейджа «раздел не найден»", () => {
    // Бэкенд прячет сентинел-id секций («preamble», «trailing», «pN») через
    // _public_section_number() — обычный риск с цитатой из преамбулы имеет
    // section_number == null, но это не missing.
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Из преамбулы", section_number: null })],
            coverage: [coverage({ rule_id: "r1", status: "risk", title: "Из преамбулы" })],
          }),
        })}
      />,
    );
    expect(screen.queryByText("раздел не найден")).toBeNull();
    // Ref column still shows "—" for a null section_number.
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("риск с section_number, но coverage-статусом missing — С бейджем «раздел не найден»", () => {
    // Ветка parsed.status == "missing" в _assess: модель вернула missing для
    // замапленной секции — section_number непустой, но правило missing.
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Missing с секцией", section_number: "5" })],
            coverage: [coverage({ rule_id: "r1", status: "missing", title: "Missing с секцией" })],
          }),
        })}
      />,
    );
    expect(screen.getByText("раздел не найден")).toBeInTheDocument();
    expect(screen.getByText("п. 5")).toBeInTheDocument();
    expect(screen.queryByText("—")).toBeNull();
  });

  it("бейдж «возможно завышен» у overstated-риска; тултип-текст присутствует по наведению", async () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Завышенный", verdict: "overstated" })],
          }),
        })}
      />,
    );
    const badge = screen.getByText("возможно завышен");
    // Один экземпляр текста — скрытый SR-span; по наведению появляется
    // второй — видимый тултип.
    expect(
      screen.getAllByText(
        "Проверка по нормам показала, что риск может быть преувеличен — прочитайте и оцените сами",
      ),
    ).toHaveLength(1);
    fireEvent.mouseOver(badge);
    await waitFor(() =>
      expect(
        screen.getAllByText(
          "Проверка по нормам показала, что риск может быть преувеличен — прочитайте и оцените сами",
        ),
      ).toHaveLength(2),
    );
  });

  it("клавиатура: фокус на кнопке-строке раскрывает тултип вердикта (WAI tooltip-on-focus)", async () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Завышенный", verdict: "overstated" })],
          }),
        })}
      />,
    );
    const row = screen.getByRole("button", { name: /Завышенный/ });
    // До фокуса текст пояснения есть ровно один раз — скрытый SR-span
    // (aria-describedby), видимого тултипа нет.
    expect(
      screen.getAllByText(
        "Проверка по нормам показала, что риск может быть преувеличен — прочитайте и оцените сами",
      ),
    ).toHaveLength(1);
    // Фокус на строке (единственный tab-stop) форсирует показ тултипа через
    // controlled `open` — TooltipDesktop не поддерживает trigger="focus"
    // нативно, см. ReviewPanel.tsx/focusedVerdict.
    fireEvent.focus(row);
    await waitFor(() =>
      expect(
        screen.getAllByText(
          "Проверка по нормам показала, что риск может быть преувеличен — прочитайте и оцените сами",
        ),
      ).toHaveLength(2),
    );
    // Пояснение — ОПИСАНИЕ строки, не имя: accessible name остаётся коротким.
    expect(row).not.toHaveAccessibleName(/Проверка по нормам/);
    expect(row).toHaveAccessibleDescription(
      "Проверка по нормам показала, что риск может быть преувеличен — прочитайте и оцените сами",
    );
  });

  it("клавиатура: фокус на строке missing-риска раскрывает тултип «раздел не найден»", async () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Без раздела", section_number: null })],
            coverage: [coverage({ rule_id: "r1", status: "missing", title: "Без раздела" })],
          }),
        })}
      />,
    );
    const row = screen.getByRole("button", { name: /Без раздела/ });
    expect(screen.getAllByText("Правило ожидает раздел в договоре, но он не найден")).toHaveLength(1);
    fireEvent.focus(row);
    await waitFor(() =>
      expect(
        screen.getAllByText("Правило ожидает раздел в договоре, но он не найден"),
      ).toHaveLength(2),
    );
    expect(row).not.toHaveAccessibleName(/Правило ожидает раздел/);
    expect(row).toHaveAccessibleDescription("Правило ожидает раздел в договоре, но он не найден");
  });

  it("«Остальные правила»: только ok/not_applicable, без дублей рисков/missing", () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r-risk", title: "Известный риск" })],
            coverage: [
              coverage({ rule_id: "c-ok", status: "ok", title: "В порядке" }),
              coverage({ rule_id: "c-na", status: "not_applicable", title: "Неприменимо" }),
              coverage({ rule_id: "c-risk", status: "risk", title: "Дублирующий риск" }),
              coverage({ rule_id: "c-missing", status: "missing", title: "Пропавшее" }),
            ],
          }),
        })}
      />,
    );
    expect(screen.getByText("В порядке")).toBeInTheDocument();
    expect(screen.getByText("Неприменимо")).toBeInTheDocument();
    expect(screen.queryByText("Дублирующий риск")).toBeNull();
    expect(screen.queryByText("Пропавшее")).toBeNull();
    // "Известный риск" must appear exactly once — in the risks accordion, not duplicated below.
    expect(screen.getAllByText("Известный риск")).toHaveLength(1);
  });

  it("Esc и кнопка ✕ диспатчат CLOSE_REVIEW_PANEL", () => {
    render(<ReviewPanel message={message({ review: report({ risks: [risk()] }) })} />);
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(closeReviewPanel).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(closeReviewPanel).toHaveBeenCalledTimes(2);
  });

  it("чипы норм — кнопки; клик открывает карточку статьи (ArticlePreview)", () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [
              risk({
                rule_id: "r1",
                title: "С цитатой",
                citations: [
                  {
                    act_short_name: "ГК РФ",
                    kind: "codex",
                    number: "450",
                    title: "Изменение договора",
                    full_text: "Полный текст статьи 450",
                    score: 0.5,
                  },
                ],
              }),
            ],
          }),
        })}
      />,
    );
    const chip = screen.getByRole("button", { name: /450/ });
    fireEvent.click(chip);
    expect(screen.getByRole("dialog", { name: /450/ })).toBeInTheDocument();
    expect(screen.getByText("Полный текст статьи 450")).toBeInTheDocument();
  });

  it("«Копировать риск» кладёт в буфер заголовок с разделом, риск, рекомендацию, основание (buildRiskText)", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [
              risk({
                rule_id: "r1",
                title: "Односторонний отказ",
                section_number: "9.1",
                explanation: "Условие ущемляет покупателя",
                recommendation: "Согласовать порядок отказа",
              }),
            ],
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Копировать риск" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        "Односторонний отказ (п. 9.1)\n\nРиск: Условие ущемляет покупателя\n\nРекомендация: Согласовать порядок отказа\n\nОснование: норма в корпусе не найдена",
      ),
    );
  });

  it("«Обсудить в чате» у риска: префилл композера и закрытие панели (Задача 5)", () => {
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [risk({ rule_id: "r1", title: "Неустойка", section_number: "6.2" })],
          }),
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Обсудить в чате" }));
    expect(prefillComposer).toHaveBeenCalledWith("Про риск «Неустойка» (п. 6.2): ");
    expect(closeReviewPanel).toHaveBeenCalledTimes(1);
  });

  it("«Копировать отчёт» в шапке кладёт в буфер полный текст отчёта (Задача 5)", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(
      <ReviewPanel
        message={message({
          review: report({ risks: [risk({ rule_id: "r1", title: "Неустойка" })] }),
        })}
      />,
    );
    const [headerCopy] = screen.getAllByRole("button", { name: "Копировать отчёт" });
    fireEvent.click(headerCopy);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("Проверка договора: Договор поставки");
    expect(copied).toContain("Сформировано в Нейроюристе");
  });

  it("низ панели: «Обсудить риски в чате» кладёт префилл по плейбуку и закрывает панель", () => {
    render(
      <ReviewPanel
        message={message({
          review: report({ risks: [risk()], playbook_name: "Договор поставки" }),
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Обсудить риски в чате" }));
    expect(prefillComposer).toHaveBeenCalledWith("Про риски из проверки «Договор поставки»: ");
    expect(closeReviewPanel).toHaveBeenCalledTimes(1);
  });

  it("низ панели: «Копировать отчёт» (текстовая кнопка) тоже кладёт полный текст в буфер", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(<ReviewPanel message={message({ review: report({ risks: [risk()] }) })} />);
    const copyButtons = screen.getAllByRole("button", { name: "Копировать отчёт" });
    expect(copyButtons).toHaveLength(2); // шапка (иконка) + низ панели (текст)
    fireEvent.click(copyButtons[1]);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  });

  it("строка риска несёт индикатор раскрытости (шеврон)", () => {
    const { container } = render(
      <ReviewPanel message={message({ review: report({ risks: [risk()] }) })} />,
    );
    expect(container.querySelector(".rvp-risk-row .rvp-chev")).toBeInTheDocument();
  });

  it("рендерит слот резюме, если report.summary задан", () => {
    const withSummary = { ...report(), summary: "Договор в целом рабочий." };
    const { rerender, container } = render(
      <ReviewPanel message={message({ review: withSummary })} />,
    );
    expect(screen.getByText("Договор в целом рабочий.")).toBeInTheDocument();
    expect(container.querySelector(".rvp-summary")).toBeInTheDocument();

    rerender(<ReviewPanel message={message({ id: "m2", review: report() })} />);
    expect(container.querySelector(".rvp-summary")).toBeNull();
  });

  it("шапка: плейбук, время из createdAt, чип файла", () => {
    render(<ReviewPanel message={message()} />);
    expect(screen.getByText(/Договор поставки/)).toBeInTheDocument();
    expect(screen.getByText("договор_поставки.pdf")).toBeInTheDocument();
  });

  it("шапка: «вы — {report.role}» рядом с чипом, когда роль известна (T-0046)", () => {
    render(<ReviewPanel message={message({ review: report({ role: "Покупатель" }) })} />);
    expect(screen.getByText("вы — Покупатель")).toBeInTheDocument();
  });

  it("шапка: без строки роли, когда report.role не задан", () => {
    const { container } = render(<ReviewPanel message={message()} />);
    expect(container.querySelector(".rvp-sub")).not.toHaveTextContent("вы —");
  });

  it("report=null (сообщение без отчёта) — панель не рендерит ничего, не падает", () => {
    const { container } = render(<ReviewPanel message={message({ review: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("меню «Скачать»: пункт DOCX ведёт на export-роут", async () => {
    render(<ReviewPanel message={message()} />);
    fireEvent.click(screen.getByRole("button", { name: "Скачать" }));
    // Popover позиционируется через react-popper, которое разрешается микротаском
    // (см. SourceSelector.test.tsx) — до этого содержимое портала скрыто.
    const link = await screen.findByRole("link", { name: "Скачать DOCX" });
    expect(link).toHaveAttribute("href", "/reviews/m1/export?format=docx");
    expect(link).toHaveAttribute("download");
  });

  it("«Сохранить в PDF»: раскрывает все риски и зовёт window.print", async () => {
    const print = vi.fn();
    vi.stubGlobal("print", print);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });
    render(
      <ReviewPanel
        message={message({
          review: report({
            risks: [
              risk({ rule_id: "r1", title: "Первый", explanation: "тело один" }),
              risk({ rule_id: "r2", title: "Второй", explanation: "тело два" }),
            ],
            coverage: [
              coverage({ rule_id: "r1", status: "risk" }),
              coverage({ rule_id: "r2", status: "risk" }),
            ],
          }),
        })}
      />,
    );
    // до печати раскрыт только первый риск
    expect(screen.queryByText("тело два")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Скачать" }));
    // Popover позиционируется асинхронно (react-popper) — см. пункт DOCX выше.
    const pdfItem = await screen.findByRole("button", { name: "Сохранить в PDF" });
    fireEvent.click(pdfItem);

    await waitFor(() => expect(print).toHaveBeenCalled());
    expect(screen.getByText("тело два")).toBeInTheDocument();
    expect(document.body.classList.contains("rvp-printing")).toBe(true);

    fireEvent(window, new Event("afterprint"));
    await waitFor(() =>
      expect(document.body.classList.contains("rvp-printing")).toBe(false),
    );
    expect(screen.queryByText("тело два")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

// -- T-0048: панель из раздела «Проверки» — опциональные пропсы --------------

describe("ReviewPanel props override (T-0048)", () => {
  it("onClose: кнопка «Закрыть» зовёт проп, а не контекст", () => {
    const onClose = vi.fn();
    render(<ReviewPanel message={message()} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(closeReviewPanel).not.toHaveBeenCalled();
  });

  it("onDiscuss: «Обсудить в чате» отдаёт затравку пропу, контекст не трогается", () => {
    const onDiscuss = vi.fn();
    render(
      <ReviewPanel
        message={message({
          review: report({ risks: [risk({ title: "Оплата", section_number: "2.2" })] }),
        })}
        onDiscuss={onDiscuss}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Обсудить в чате" }));
    expect(onDiscuss).toHaveBeenCalledWith('Про риск «Оплата» (п. 2.2): ');
    expect(prefillComposer).not.toHaveBeenCalled();
    expect(closeReviewPanel).not.toHaveBeenCalled();
  });

  it("doc-проп заменяет поиск по state.documents (в т.ч. явный null)", () => {
    const other: HubDocumentInfo = { ...documents[0], id: "dX", filename: "иной_файл.docx", parser: "docx" };
    const { container, rerender } = render(<ReviewPanel message={message()} doc={other} />);
    expect(container.querySelector(".rvp-sub")).toHaveTextContent("иной_файл.docx");
    rerender(<ReviewPanel message={message()} doc={null} />);
    expect(container.querySelector(".rvp-sub")).not.toHaveTextContent("договор_поставки.pdf");
  });
});
