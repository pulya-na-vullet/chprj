import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

const todayIso = new Date().toISOString();

// view переключается между тестами: подсветка активной беседы гейтится
// видом чата (T-0053).
let view = "chat";

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({
    state: {
      conversations: [{ id: "1", title: "Договор аренды", updated_at: todayIso }],
      currentId: "1",
      conversationsStatus: "ready",
      conversationsError: null,
      view,
    },
    openConversation: vi.fn(),
    removeConversation: vi.fn(),
    retryConversations: vi.fn(),
  }),
}));

import { ConversationList } from "../components/ConversationList";

describe("ConversationList grouping", () => {
  it("renders a time-group header for today's conversation", () => {
    view = "chat";
    render(<ConversationList />);
    expect(screen.getByText("Сегодня")).toBeInTheDocument();
    expect(screen.getByText("Договор аренды")).toBeInTheDocument();
  });
});

describe("ConversationList active highlight (T-0053)", () => {
  it("текущая беседа подсвечена только в виде чата", () => {
    view = "chat";
    const { container, unmount } = render(<ConversationList />);
    expect(container.querySelector(".conv-item-active")).not.toBeNull();
    unmount();

    // открыт раздел («Проверки»/«Файлы»/«Источники») — выделение снимается
    view = "reviews";
    const { container: c2 } = render(<ConversationList />);
    expect(c2.querySelector(".conv-item-active")).toBeNull();
  });
});
