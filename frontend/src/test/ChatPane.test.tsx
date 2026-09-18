import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ChatPane } from "../components/ChatPane";

/**
 * The first-message error case used to be invisible: `ChatPane` short-circuited
 * to HomeState whenever `messages.length === 0`, so a TURN_FAILED that left
 * empty history showed nothing. We render the banner in both branches.
 */

// HomeState читает профиль для приветствия (T-0128) — auth мокается всегда.
vi.mock("../state/AuthContext", () => ({
  useAuth: () => ({
    state: {
      status: "authenticated",
      user: { id: "u1", email: "a@b.ru" },
      sessionExpired: false,
    },
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("../state/ChatContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state/ChatContext")>();
  return {
    ...actual,
    useChat: vi.fn(() => ({
      state: {
        conversations: [],
        currentId: null,
        messages: [],
        streaming: false,
        working: null,
        draftAnswer: "",
        draftCitations: [],
        pendingUser: null,
        acts: [],
        actsFull: [],
        documents: [],
        reviewProgress: null,
        selectedSources: [],
        banner: "Ошибка первого сообщения",
        sidebarCollapsed: false,
        turnId: 1,
      },
      send: vi.fn(),
      openConversation: vi.fn(),
      newChat: vi.fn(),
      removeConversation: vi.fn(),
      toggleSidebar: vi.fn(),
      toggleSource: vi.fn(),
    })),
  };
});

describe("ChatPane banner", () => {
  it("renders the banner in empty state when present", () => {
    render(<ChatPane />);
    expect(screen.getByText("Ошибка первого сообщения")).toBeInTheDocument();
  });
});
