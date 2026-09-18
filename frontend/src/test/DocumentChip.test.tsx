import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";

import { DocumentChip } from "../components/DocumentChip";
import type { HubDocumentInfo, PlaybookInfo } from "../api/types";

const sendReview = vi.fn();
const focusComposer = vi.fn();
const updateDocument = vi.fn();
const clearAttachIntent = vi.fn();
let attachIntent: { docId: string; intent: "review" | "ask" } | null = null;

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({
    state: { streaming: false, attachIntent },
    sendReview,
    focusComposer,
    updateDocument,
    clearAttachIntent,
  }),
}));

const playbooks: PlaybookInfo[] = [
  { id: "supply_ru", name: "Договор поставки", rules_count: 12, roles: ["Покупатель", "Поставщик"] },
];

vi.mock("../api/client", () => ({
  listPlaybooks: vi.fn(() => Promise.resolve(playbooks)),
  getDocument: vi.fn(),
}));

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1",
    owner_id: "u1",
    filename: "договор_поставки.pdf",
    content_type: "application/pdf",
    size: 2048,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    summary: null,
    created_at: "2026-07-19T00:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  sendReview.mockClear();
  focusComposer.mockClear();
  clearAttachIntent.mockClear();
  attachIntent = null;
});

describe("DocumentChip: два сценария (T-0050)", () => {
  it("клик по чипу открывает экран сценариев с двумя пунктами и именем файла", () => {
    render(<DocumentChip document={doc()} />);
    fireEvent.click(screen.getByRole("button", { name: /договор_поставки\.pdf/ }));

    // T-0053: head с именем файла убран — оно и так на чипе под меню
    expect(document.querySelector(".doc-menu .doc-menu-head")).toBeNull();
    expect(screen.getByRole("menuitem", { name: /Проверить на риски/ })).toBeInTheDocument();
    expect(screen.getByText("Отчет со ссылками на нормы права")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Задать вопрос по документу/ })).toBeInTheDocument();
    expect(screen.getByText("Ответы по тексту документа")).toBeInTheDocument();
    // плейбуки на этом экране ещё не показываются
    expect(screen.queryByText("Договор поставки")).not.toBeInTheDocument();
  });

  it("«Проверить на риски» ведёт на экран плейбуков; выбор зовёт sendReview", async () => {
    render(<DocumentChip document={doc()} />);
    fireEvent.click(screen.getByRole("button", { name: /договор_поставки\.pdf/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Проверить на риски/ }));

    const pb = await screen.findByRole("menuitem", { name: /Договор поставки/ });
    expect(screen.getByText("Проверить на риски", { selector: ".doc-menu-head" })).toBeInTheDocument();
    fireEvent.click(pb);
    expect(sendReview).toHaveBeenCalledWith(
      "d1",
      "supply_ru",
      "Проверить «договор_поставки.pdf»: Договор поставки",
    );
  });

  it("«Задать вопрос по документу» закрывает меню и фокусирует композер, ничего не отправляя", () => {
    render(<DocumentChip document={doc()} />);
    fireEvent.click(screen.getByRole("button", { name: /договор_поставки\.pdf/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Задать вопрос по документу/ }));

    expect(focusComposer).toHaveBeenCalledTimes(1);
    expect(sendReview).not.toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("повторное открытие меню снова начинается с экрана сценариев", async () => {
    render(<DocumentChip document={doc()} />);
    const chip = screen.getByRole("button", { name: /договор_поставки\.pdf/ });
    fireEvent.click(chip);
    fireEvent.click(screen.getByRole("menuitem", { name: /Проверить на риски/ }));
    await screen.findByRole("menuitem", { name: /Договор поставки/ });
    fireEvent.click(chip); // закрыть
    fireEvent.click(chip); // открыть снова

    expect(screen.getByRole("menuitem", { name: /Проверить на риски/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Договор поставки/ })).not.toBeInTheDocument();
  });

  it("ошибка загрузки плейбуков не остаётся висеть после успешного ретрая", async () => {
    // Свежие модули: кэш loadPlaybooks в DocumentChip модульный, а прочие
    // тесты уже прогрели его успешным промисом.
    vi.resetModules();
    const apiFresh = await import("../api/client");
    vi.mocked(apiFresh.listPlaybooks).mockRejectedValueOnce(new Error("net"));
    const { DocumentChip: FreshChip } = await import("../components/DocumentChip");

    render(<FreshChip document={doc()} />);
    const chip = screen.getByRole("button", { name: /договор_поставки\.pdf/ });
    fireEvent.click(chip);
    fireEvent.click(screen.getByRole("menuitem", { name: /Проверить на риски/ }));
    await screen.findByText("Не удалось загрузить плейбуки");

    fireEvent.click(chip); // закрыть
    fireEvent.click(chip); // открыть снова — экран сценариев
    fireEvent.click(screen.getByRole("menuitem", { name: /Проверить на риски/ }));

    await screen.findByRole("menuitem", { name: /Договор поставки/ });
    expect(screen.queryByText("Не удалось загрузить плейбуки")).not.toBeInTheDocument();
  });
});


describe("DocumentChip attach intent (T-0054)", () => {
  it("review-интент: готовый документ сам открывает выбор плейбука и гасит интент", async () => {
    attachIntent = { docId: "d1", intent: "review" };
    render(<DocumentChip document={doc({ status: "ready" })} />);

    expect(await screen.findByRole("menuitem", { name: /Договор поставки/ })).toBeInTheDocument();
    expect(screen.getByText("Проверить на риски", { selector: ".doc-menu-head" })).toBeInTheDocument();
    expect(clearAttachIntent).toHaveBeenCalled();
  });

  it("интент чужого документа чип не трогает", () => {
    attachIntent = { docId: "other", intent: "review" };
    render(<DocumentChip document={doc({ status: "ready" })} />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(clearAttachIntent).not.toHaveBeenCalled();
  });

  it("ask-интент просто гасится без открытия меню", () => {
    attachIntent = { docId: "d1", intent: "ask" };
    render(<DocumentChip document={doc({ status: "ready" })} />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(clearAttachIntent).toHaveBeenCalled();
  });
});
