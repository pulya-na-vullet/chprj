// Провайдер тура (T-0132): свёрнутый сайдбар разворачивается перед стартом
// (зафиксированное решение критерия приёмки), «Пропустить» и финал ставят
// отметку через PATCH /profile (saveProfile), автозапуска при выставленной
// tour_completed_at нет.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { TourProvider, useTour } from "../components/tour/TourProvider";

const toggleSidebar = vi.fn();
const setComposerPulse = vi.fn();
const prefillComposer = vi.fn();
const saveProfile = vi.fn(() => Promise.resolve());

let sidebarCollapsed = false;
let tourCompletedAt: string | null = null;
let questionsAsked = 0;

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({
    state: {
      sidebarCollapsed,
      view: "chat",
      currentId: null,
      questionsSentInSession: 0,
    },
    toggleSidebar,
    setComposerPulse,
    prefillComposer,
  }),
}));

vi.mock("../state/AuthContext", () => ({
  useAuth: () => ({
    state: {
      status: "authenticated",
      user: {
        id: "u1",
        email: "a@b.ru",
        questions_asked: questionsAsked,
        tour_completed_at: tourCompletedAt,
      },
      sessionExpired: false,
    },
    saveProfile,
  }),
}));

function Probe() {
  const tour = useTour();
  return (
    <div>
      <span data-testid="status">{tour.state.status}</span>
      <span data-testid="pill-visible">{String(tour.pillVisible)}</span>
      <button type="button" onClick={tour.start}>
        probe-start
      </button>
      <button type="button" onClick={tour.next}>
        probe-next
      </button>
      <button type="button" onClick={tour.skip}>
        probe-skip
      </button>
    </div>
  );
}

function renderProvider() {
  render(
    <TourProvider>
      <Probe />
    </TourProvider>,
  );
}

beforeEach(() => {
  toggleSidebar.mockClear();
  setComposerPulse.mockClear();
  prefillComposer.mockClear();
  saveProfile.mockClear();
  sidebarCollapsed = false;
  tourCompletedAt = "2026-08-12T00:00:00Z"; // без автозапуска по умолчанию
  questionsAsked = 0;
  window.localStorage.clear();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
});

describe("TourProvider (T-0132)", () => {
  it("старт при свёрнутом сайдбаре сначала разворачивает его", () => {
    sidebarCollapsed = true;
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
    expect(toggleSidebar).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("status")).toHaveTextContent("steps");
  });

  it("при развёрнутом сайдбаре тумблер не дёргается", () => {
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
    expect(toggleSidebar).not.toHaveBeenCalled();
  });

  it("«Пропустить» ставит отметку tour_completed через PATCH /profile", () => {
    tourCompletedAt = null;
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
    fireEvent.click(screen.getByRole("button", { name: "probe-skip" }));
    expect(saveProfile).toHaveBeenCalledWith({ tour_completed: true });
    expect(screen.getByTestId("status")).toHaveTextContent("done");
  });

  it("финал (4 × «Далее») тоже ставит отметку", () => {
    tourCompletedAt = null;
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
    for (let i = 0; i < 4; i += 1) {
      fireEvent.click(screen.getByRole("button", { name: "probe-next" }));
    }
    expect(screen.getByTestId("status")).toHaveTextContent("finale");
    expect(saveProfile).toHaveBeenCalledWith({ tour_completed: true });
  });

  it("повторный финал «тихий»: без автонабора вопроса и пульса отправки", () => {
    vi.useFakeTimers();
    try {
      // Отметка уже стоит — это перезапуск с пилюли.
      renderProvider();
      fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
      for (let i = 0; i < 4; i += 1) {
        fireEvent.click(screen.getByRole("button", { name: "probe-next" }));
      }
      vi.advanceTimersByTime(10_000);
      expect(prefillComposer).not.toHaveBeenCalled();
      // setComposerPulse(false) на старте — допустим; включения быть не должно.
      expect(setComposerPulse).not.toHaveBeenCalledWith(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("первый финал печатает вопрос и включает пульс", () => {
    vi.useFakeTimers();
    try {
      tourCompletedAt = null;
      renderProvider();
      fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
      for (let i = 0; i < 4; i += 1) {
        fireEvent.click(screen.getByRole("button", { name: "probe-next" }));
      }
      vi.advanceTimersByTime(10_000);
      expect(prefillComposer).toHaveBeenCalled();
      expect(setComposerPulse).toHaveBeenCalledWith(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("порог 3 вопросов прячет пилюлю в покое, но не во время тура", () => {
    questionsAsked = 5;
    renderProvider();
    expect(screen.getByTestId("pill-visible")).toHaveTextContent("false");
    fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
    expect(screen.getByTestId("pill-visible")).toHaveTextContent("true");
  });

  it("отметка уже стоит — повторный PATCH не шлётся", () => {
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: "probe-start" }));
    fireEvent.click(screen.getByRole("button", { name: "probe-skip" }));
    expect(saveProfile).not.toHaveBeenCalled();
  });
});
