import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { MessageList } from "../components/MessageList";
import type { Message } from "../api/types";

// jsdom doesn't implement scrollIntoView — MessageList calls it in an effect
// on every render (auto-scroll to the newest message).
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * T-0046: MessageList computes AskBlock's `active` (last message + not
 * streaming) and wires onAskPick/onAskFree/onAskRetry to the ChatContext
 * functions those buttons actually need — coverage AssistantMessage/AskBlock
 * unit tests (which pass props directly) can't provide on their own.
 */

const sendReview = vi.fn();
const answerAsk = vi.fn();
const focusComposer = vi.fn();
const openReviewPanel = vi.fn();
const send = vi.fn();

function askMessage(over: Partial<Message> = {}): Message {
  return {
    id: "m1",
    role: "assistant",
    content: "Кто вы по этому договору?",
    citations: null,
    stopped: false,
    created_at: "2026-07-18T14:00:00",
    ask: {
      kind: "review_role",
      template: false,
      question: "Кто вы по этому договору?",
      options: ["Покупатель", "Поставщик"],
    },
    ...over,
  };
}

let currentState: Record<string, unknown> = {};

vi.mock("../state/ChatContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state/ChatContext")>();
  return {
    ...actual,
    useChat: vi.fn(() => ({
      state: currentState,
      sendReview,
      answerAsk,
      focusComposer,
      openReviewPanel,
      send,
    })),
  };
});

function baseState(over: Record<string, unknown> = {}) {
  return {
    messages: [],
    pendingUser: null,
    streaming: false,
    reviewProgress: null,
    reviewFailed: null,
    lastReviewRequest: null,
    documents: [],
    acts: [],
    actsFull: [],
    working: null,
    draftAnswer: "",
    draftCitations: [],
    draftWebSources: [],
    draftReview: null,
    ...over,
  };
}

describe("MessageList ask wiring (T-0046)", () => {
  it("ask on the last message, not streaming — AskBlock buttons are enabled", () => {
    currentState = baseState({ messages: [askMessage()] });
    render(<MessageList />);
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeEnabled();
  });

  it("ask on a non-last message — AskBlock buttons render disabled", () => {
    currentState = baseState({
      messages: [
        askMessage({ id: "m1" }),
        { ...askMessage({ id: "m2" }), ask: null, content: "следующий вопрос" },
      ],
    });
    render(<MessageList />);
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeDisabled();
  });

  it("streaming=true — even the last ask message's buttons render disabled", () => {
    currentState = baseState({ messages: [askMessage()], streaming: true });
    render(<MessageList />);
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeDisabled();
  });

  it("clicking an option calls answerAsk(ask, text)", () => {
    currentState = baseState({ messages: [askMessage()] });
    render(<MessageList />);
    fireEvent.click(screen.getByRole("button", { name: "Покупатель" }));
    expect(answerAsk).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "review_role" }),
      "Покупатель",
    );
  });

  it("clicking «Другое — напишу сам» calls focusComposer", () => {
    currentState = baseState({ messages: [askMessage()] });
    render(<MessageList />);
    fireEvent.click(screen.getByRole("button", { name: "Другое — напишу сам" }));
    expect(focusComposer).toHaveBeenCalledTimes(1);
  });

  it("review_failed ask retry calls sendReview with document_id/playbook_id/role from the persisted ask", () => {
    sendReview.mockClear();
    currentState = baseState({
      messages: [
        askMessage({
          content: "Документ не найден",
          ask: {
            kind: "review_failed",
            template: false,
            document_id: "d1",
            playbook_id: "supply_ru",
            role: "Покупатель",
            error: "Документ не найден",
          },
        }),
      ],
    });
    render(<MessageList />);
    fireEvent.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(sendReview).toHaveBeenCalledWith("d1", "supply_ru", "Повторить проверку", "Покупатель");
  });

  it("review_failed retry uses the doc filename in the label when the document is known", () => {
    sendReview.mockClear();
    currentState = baseState({
      documents: [
        {
          id: "d1",
          owner_id: "default",
          filename: "договор.pdf",
          content_type: "application/pdf",
          size: 10,
          status: "ready",
          parser: "pdf",
          page_count: null,
          error: null,
          summary: null,
          created_at: "2026-07-08T00:00:00Z",
        },
      ],
      messages: [
        askMessage({
          content: "Документ не найден",
          ask: {
            kind: "review_failed",
            template: false,
            document_id: "d1",
            playbook_id: "supply_ru",
            role: "Покупатель",
            error: "Документ не найден",
          },
        }),
      ],
    });
    render(<MessageList />);
    fireEvent.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(sendReview).toHaveBeenCalledWith("d1", "supply_ru", "Проверить «договор.pdf»", "Покупатель");
  });

  it("ask_user: кнопка-вариант шлёт обычное сообщение, «Другое» фокусирует композер (T-0051)", () => {
    send.mockClear();
    focusComposer.mockClear();
    sendReview.mockClear();
    currentState = baseState({
      messages: [
        askMessage({
          content: "Для кого письмо?",
          ask: {
            kind: "ask_user",
            template: false,
            question: "Для кого письмо?",
            options: ["Клиенту", "Суду"],
          },
        }),
      ],
    });
    render(<MessageList />);
    fireEvent.click(screen.getByRole("button", { name: "Клиенту" }));
    expect(send).toHaveBeenCalledWith("Клиенту");
    expect(sendReview).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Другое — напишу сам" }));
    expect(focusComposer).toHaveBeenCalled();
  });
});
