import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { HomeState } from "../components/HomeState";

const conversations = [
  {
    id: "c1",
    title: "Проверь договор поставки",
    updated_at: new Date().toISOString(),
    preview: "Проверка по плейбуку Поставка — Риски: high 2, medium 3",
  },
  { id: "c2", title: "Новый чат", updated_at: new Date().toISOString(), preview: null },
];

vi.mock("../state/ChatContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state/ChatContext")>();
  return {
    ...actual,
    useChat: vi.fn(() => ({
      state: {
        conversations,
        currentId: null,
        messages: [],
        streaming: false,
        stopping: false,
        working: null,
        draftAnswer: "",
        draftCitations: [],
        pendingUser: null,
        acts: [],
        actsFull: [],
        documents: [],
        reviewProgress: null,
        selectedSources: [],
        banner: null,
        sidebarCollapsed: false,
        turnId: 0,
      },
      send: vi.fn(),
      stop: vi.fn(),
      uploadFile: vi.fn(),
      setBanner: vi.fn(),
      openConversation: vi.fn(),
    })),
  };
});

// Приветствие по имени (T-0128): профиль меняется per-test.
let authUser: Record<string, unknown> = { id: "u1", email: "a@b.ru" };

vi.mock("../state/AuthContext", () => ({
  useAuth: () => ({
    state: { status: "authenticated", user: authUser, sessionExpired: false },
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

describe("Реестр задач: превью (T-0014)", () => {
  it("показывает итог последнего ответа и «Без ответа» для пустой беседы", () => {
    render(<HomeState />);
    expect(
      screen.getByText("Проверка по плейбуку Поставка — Риски: high 2, medium 3"),
    ).toBeInTheDocument();
    expect(screen.getByText("Без ответа")).toBeInTheDocument();
  });
});

describe("Приветствие по имени (T-0128)", () => {
  it("без имени — нейтральный заголовок", () => {
    authUser = { id: "u1", email: "a@b.ru" };
    render(<HomeState />);
    expect(screen.getByRole("heading", { name: "С чего начнём?" })).toBeInTheDocument();
  });

  it("с именем — «{Имя}, с чего начнём?»", () => {
    authUser = { id: "u1", email: "a@b.ru", first_name: "Денис" };
    render(<HomeState />);
    expect(screen.getByRole("heading", { name: "Денис, с чего начнём?" })).toBeInTheDocument();
  });
});
