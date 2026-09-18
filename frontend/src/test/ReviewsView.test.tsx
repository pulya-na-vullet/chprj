import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ReviewsView } from "../components/reviews/ReviewsView";
import * as api from "../api/client";
import type { Message, ReviewListItem } from "../api/types";

const openConversation = vi.fn();
const prefillComposer = vi.fn();
const startReviewFromSection = vi.fn();
const clearReviewRequest = vi.fn();

const idleChatState = {
  reviewProgress: null,
  lastReviewRequest: null,
  streaming: false,
  turnId: 0,
  documents: [],
  reviewRequestDocId: null,
};
let chatState: Record<string, unknown> = idleChatState;

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({
    state: chatState,
    openConversation,
    prefillComposer,
    startReviewFromSection,
    clearReviewRequest,
  }),
}));

function item(over: Partial<ReviewListItem> = {}): ReviewListItem {
  return {
    message_id: "m1",
    conversation_id: "c1",
    playbook_id: "supply_ru",
    playbook_name: "Договор поставки",
    document_id: "d1",
    document_filename: "договор_поставки.pdf",
    document_parser: "pdf",
    role: "Покупатель",
    status: "done",
    high: 2,
    medium: 1,
    low: 0,
    rules_total: 12,
    error: null,
    created_at: "2026-07-18T14:32:00+00:00",
    ...over,
  };
}

function reportMessage(): Message {
  return {
    id: "m1",
    role: "assistant",
    content: "",
    citations: null,
    stopped: false,
    created_at: "2026-07-18T14:32:00+00:00",
    review: {
      coverage: [],
      disclaimer: "Черновая проверка.",
      document_id: "d1",
      playbook_id: "supply_ru",
      playbook_name: "Договор поставки",
      risks: [],
      role: "Покупатель",
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  openConversation.mockClear();
  prefillComposer.mockClear();
  startReviewFromSection.mockClear();
  clearReviewRequest.mockClear();
  chatState = idleChatState;
});

describe("ReviewsView", () => {
  it("рендерит таблицу: плейбук с ролью, документ, счётчики, дата", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [item()], total: 1 });
    const { container } = render(<ReviewsView />);
    expect(await screen.findByText("Договор поставки")).toBeInTheDocument();
    expect(screen.getByText("вы — Покупатель")).toBeInTheDocument();
    expect(screen.getByText("договор_поставки.pdf")).toBeInTheDocument();
    const counts = container.querySelector(".rvs-counts");
    expect(counts).toHaveTextContent("2");
    expect(counts).toHaveTextContent("1");
    // нулевой уровень (low=0) не рендерится
    expect(counts?.querySelectorAll(".rvs-lvl")).toHaveLength(2);
  });

  it("failed-строка: «проверка не удалась», клик не открывает панель", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({
      items: [item({ status: "failed", error: "Сервис недоступен", high: 0, medium: 0 })],
      total: 1,
    });
    const getMessages = vi.spyOn(api, "getMessages");
    const { container } = render(<ReviewsView />);
    expect(await screen.findByText("проверка не удалась")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Договор поставки"));
    expect(getMessages).not.toHaveBeenCalled();
    expect(container.querySelector(".rvp-panel")).toBeNull();
  });

  it("роль не указана — подстрока-заглушка", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [item({ role: null })], total: 1 });
    render(<ReviewsView />);
    expect(await screen.findByText("роль не указана")).toBeInTheDocument();
  });

  it("удалённый документ — заглушка вместо имени", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({
      items: [item({ document_filename: null, document_parser: null })],
      total: 1,
    });
    render(<ReviewsView />);
    expect(await screen.findByText("документ удалён")).toBeInTheDocument();
  });

  it("поиск фильтрует по документу и плейбуку", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({
      items: [
        item(),
        item({
          message_id: "m2",
          conversation_id: "c2",
          playbook_name: "Аренда",
          document_filename: "аренда_офис.docx",
        }),
      ],
      total: 2,
    });
    render(<ReviewsView />);
    await screen.findByText("Аренда");
    fireEvent.change(screen.getByPlaceholderText(/Найти проверку/), {
      target: { value: "аренда" },
    });
    expect(screen.queryByText("Договор поставки")).toBeNull();
    expect(screen.getByText("Аренда")).toBeInTheDocument();
  });

  it("клик по done-строке открывает панель отчёта", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [item()], total: 1 });
    vi.spyOn(api, "getMessages").mockResolvedValue([reportMessage()]);
    const { container } = render(<ReviewsView />);
    fireEvent.click(await screen.findByText("Договор поставки"));
    await waitFor(() => expect(container.querySelector(".rvp-panel")).not.toBeNull());
    expect(container.querySelector(".rvp-title")).toHaveTextContent("Договор поставки");
  });

  it("«Обсудить» из панели раздела открывает беседу и префиллит композер", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [item()], total: 1 });
    vi.spyOn(api, "getMessages").mockResolvedValue([reportMessage()]);
    openConversation.mockResolvedValue(undefined);
    render(<ReviewsView />);
    fireEvent.click(await screen.findByText("Договор поставки"));
    fireEvent.click(await screen.findByRole("button", { name: "Обсудить риски в чате" }));
    await waitFor(() => expect(openConversation).toHaveBeenCalledWith("c1"));
    await waitFor(() =>
      expect(prefillComposer).toHaveBeenCalledWith("Про риски из проверки «Договор поставки»: "),
    );
  });

  it("«Новая проверка» открывает диалог; запуск уходит в контекст с ярлыком чата", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    vi.spyOn(api, "listPlaybooks").mockResolvedValue([]);
    render(<ReviewsView />);
    fireEvent.click(await screen.findByRole("button", { name: /Новая проверка/ }));
    // Диалог открыт: секция «Плейбук» есть всегда (поле роли теперь условное —
    // показывается только для плейбуков с ролями, см. T-0070).
    expect(await screen.findByText("Плейбук")).toBeInTheDocument();
  });

  it("живой прогресс: синтетическая строка активного прогона этой сессии", async () => {
    chatState = {
      ...idleChatState,
      streaming: true,
      turnId: 5,
      reviewProgress: { rule_id: "r", title: "Оплата", index: 2, total: 12, status: "running" },
      lastReviewRequest: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "Проверить «файл.pdf»: Договор поставки",
        turnId: 5,
        role: "Покупатель",
      },
    };
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [], total: 0 });
    const { container } = render(<ReviewsView />);
    await screen.findByText("идёт · 2 из 12");
    expect(container.querySelector(".rvs-row-live")).toHaveTextContent("Договор поставки");
    expect(container.querySelector(".rvs-row-live")).toHaveTextContent("файл.pdf");
    expect(container.querySelector(".rvs-row-live")).toHaveTextContent("вы — Покупатель");
    expect(container.querySelector(".rvs-row-live")).toHaveTextContent("сейчас");
  });

  it("чужой (не-review) стрим синтетической строки не даёт", async () => {
    chatState = {
      ...idleChatState,
      streaming: true,
      turnId: 6,
      lastReviewRequest: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "Проверить «файл.pdf»: Договор поставки",
        turnId: 5, // прогон прошлого хода — не текущий
        role: null,
      },
    };
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [], total: 0 });
    const { container } = render(<ReviewsView />);
    await screen.findByText("Проверок ещё не было");
    expect(container.querySelector(".rvs-row-live")).toBeNull();
  });

  it("сбой запуска новой проверки показывает ошибку, а не молчит", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      {
        id: "d1",
        owner_id: "u",
        filename: "договор.docx",
        content_type: "x",
        size: 1,
        status: "ready",
        parser: "docx",
        page_count: null,
        error: null,
        summary: null,
        created_at: "2026-07-18T10:00:00Z",
      },
    ]);
    vi.spyOn(api, "listPlaybooks").mockResolvedValue([
      { id: "supply_ru", name: "Договор поставки", rules_count: 12, roles: ["Покупатель"] },
    ]);
    startReviewFromSection.mockRejectedValue(new Error("attach down"));
    render(<ReviewsView />);
    fireEvent.click(await screen.findByRole("button", { name: /Новая проверка/ }));
    fireEvent.click(await screen.findByRole("radio", { name: /договор\.docx/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Договор поставки/ }));
    fireEvent.click(screen.getByRole("button", { name: "Покупатель" }));
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));
    expect(await screen.findByText(/Не удалось запустить проверку/)).toBeInTheDocument();
  });

  it("пустое состояние", async () => {
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [], total: 0 });
    render(<ReviewsView />);
    expect(await screen.findByText("Проверок ещё не было")).toBeInTheDocument();
  });

  it("ошибка загрузки — повторить", async () => {
    const spy = vi.spyOn(api, "listReviews").mockRejectedValueOnce(new Error("x"));
    spy.mockResolvedValueOnce({ items: [item()], total: 1 });
    render(<ReviewsView />);
    fireEvent.click(await screen.findByRole("button", { name: "Повторить" }));
    expect(await screen.findByText("Договор поставки")).toBeInTheDocument();
  });

  // I5 / T-0148 (финальное ревью): запрос «Проверить на риски» из «Файлов»
  // (state.reviewRequestDocId) открывает диалог сам, с уже выбранным
  // документом, и гасит запрос — без этого тест мок useChat пропускал
  // сломанную проводку (clearReviewRequest не было в моке вовсе).
  it("запрос из «Файлов» открывает диалог с предвыбранным документом и гасится", async () => {
    chatState = { ...idleChatState, reviewRequestDocId: "d9" };
    vi.spyOn(api, "listReviews").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      {
        id: "d9",
        owner_id: "u",
        filename: "договор.docx",
        content_type: "x",
        size: 1,
        status: "ready",
        parser: "docx",
        page_count: null,
        error: null,
        summary: null,
        created_at: "2026-07-18T10:00:00Z",
      },
    ]);
    vi.spyOn(api, "listPlaybooks").mockResolvedValue([]);
    render(<ReviewsView />);

    // Диалог открылся сам, без клика «Новая проверка».
    expect(await screen.findByText("Плейбук")).toBeInTheDocument();
    await waitFor(() => expect(clearReviewRequest).toHaveBeenCalledOnce());

    const radio = (await screen.findByRole("radio", {
      name: /договор\.docx/,
    })) as HTMLInputElement;
    expect(radio.checked).toBe(true);
  });
});
