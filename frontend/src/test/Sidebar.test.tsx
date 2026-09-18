import { render, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { Sidebar } from "../components/Sidebar";

const toggleSidebar = vi.fn();
const logout = vi.fn();

const baseState = {
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
  selectedSources: [],
  banner: null,
  sidebarCollapsed: false,
  view: "chat" as const,
  sidebarWidth: 264,
  turnId: 0,
  actsStatus: "ready" as const,
  actsError: null,
  conversationsStatus: "ready" as const,
  conversationsError: null,
};

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({
    state: baseState,
    send: vi.fn(),
    openConversation: vi.fn(),
    newChat: vi.fn(),
    removeConversation: vi.fn(),
    toggleSidebar,
    setView: vi.fn(),
    setSidebarWidth: vi.fn(),
    toggleSource: vi.fn(),
    retryActs: vi.fn(),
    retryConversations: vi.fn(),
  }),
}));

// Профильные поля меняются per-test (T-0128): пустой профиль → буква+почта,
// заполненный → аватар-пресет с инициалами и имя.
let authUser: Record<string, unknown> = { id: "u1", email: "a@b.ru" };

vi.mock("../state/AuthContext", () => ({
  useAuth: () => ({
    state: { status: "authenticated", user: authUser, sessionExpired: false },
    login: vi.fn(),
    logout,
  }),
}));

function setViewport(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

describe("Sidebar Escape", () => {
  beforeEach(() => {
    toggleSidebar.mockClear();
  });
  afterEach(() => {
    setViewport(false); // reset
  });

  it("closes the drawer on Escape when the viewport is mobile", () => {
    setViewport(true);
    render(<Sidebar />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(toggleSidebar).toHaveBeenCalledTimes(1);
  });

  it("ignores Escape on desktop viewport", () => {
    setViewport(false);
    render(<Sidebar />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(toggleSidebar).not.toHaveBeenCalled();
  });
});

describe("Sidebar buttons", () => {
  afterEach(() => {
    baseState.sidebarCollapsed = false;
  });

  it("рендерит кнопку новой задачи и тумблер", () => {
    setViewport(false);
    render(<Sidebar />);
    expect(screen.getByRole("button", { name: "Новая задача" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Свернуть" })).toBeInTheDocument();
  });

  // T-0143: в свёрнутом виде CSS прячет подписи разделов — имена должны
  // остаться в доступном дереве, иначе это четыре безымянные кнопки.
  // Проверяем именно aria-label: jsdom не применяет sidebar.css, поэтому
  // getByRole нашёл бы кнопку по видимому тексту и без атрибута — такой
  // тест пережил бы снятие фикса.
  it("разделы навигации названы и в свёрнутом сайдбаре", () => {
    setViewport(false);
    baseState.sidebarCollapsed = true;
    render(<Sidebar />);
    for (const name of ["Источники права", "Проверки", "Файлы", "Шаблоны"]) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-label", name);
    }
  });

  it("тумблер панели меняет имя по состоянию", () => {
    setViewport(false);
    baseState.sidebarCollapsed = true;
    render(<Sidebar />);
    expect(screen.getByRole("button", { name: "Развернуть" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Свернуть" })).not.toBeInTheDocument();
  });
});

describe("Sidebar user block", () => {
  beforeEach(() => {
    logout.mockClear();
    authUser = { id: "u1", email: "a@b.ru" };
  });

  it("shows the current user's email", () => {
    setViewport(false);
    render(<Sidebar />);
    expect(screen.getByText("a@b.ru")).toBeInTheDocument();
  });

  it("calls logout when «Выйти» is clicked", () => {
    setViewport(false);
    render(<Sidebar />);
    fireEvent.click(screen.getByRole("button", { name: "Выйти" }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("с профилем показывает имя и инициалы на аватар-пресете (T-0128)", () => {
    authUser = {
      id: "u1",
      email: "a@b.ru",
      first_name: "Денис",
      last_name: "Анастасьев",
      avatar_preset: 2,
    };
    setViewport(false);
    render(<Sidebar />);
    expect(screen.getByText("Денис Анастасьев")).toBeInTheDocument();
    expect(screen.getByText("ДА")).toBeInTheDocument();
    expect(screen.queryByText("a@b.ru")).not.toBeInTheDocument();
  });

  it("с одним именем показывает имя и одну букву-инициал", () => {
    authUser = { id: "u1", email: "a@b.ru", first_name: "Ася" };
    setViewport(false);
    render(<Sidebar />);
    expect(screen.getByText("Ася")).toBeInTheDocument();
    expect(screen.getByText("А")).toBeInTheDocument();
  });
});
