// Тур как модальный диалог (T-0143): фокус забирается на «Далее», Tab заперт
// внутри карточки, после закрытия фокус возвращается инициатору. Без этого
// клавиатурный пользователь управляет затемнённым приложением, которого не
// видит: блокер перехватывает только мышь.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { TourOverlay } from "../components/tour/TourOverlay";
import type { TourState } from "../tour/tourMachine";

const tour = {
  state: { status: "steps", step: 0, maxSeen: 1, skipped: false } as TourState,
  pillVisible: true,
  pillText: "1/4",
  celebrate: false,
  start: vi.fn(),
  next: vi.fn(),
  skip: vi.fn(),
};

vi.mock("../components/tour/TourProvider", () => ({
  useTour: () => tour,
}));

function setState(state: TourState) {
  tour.state = state;
}

const STEPS: TourState = { status: "steps", step: 0, maxSeen: 1, skipped: false };
const DONE: TourState = { status: "done", step: 0, maxSeen: 4, skipped: false };

describe("TourOverlay: фокус (T-0143)", () => {
  it("объявлен модальным и забирает фокус на «Далее»", () => {
    setState(STEPS);
    render(<TourOverlay />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Далее" })).toHaveFocus();
  });

  it("Tab не выпускает фокус из карточки", () => {
    setState(STEPS);
    render(<TourOverlay />);
    const next = screen.getByRole("button", { name: "Далее" });
    const skip = screen.getByRole("button", { name: "Пропустить" });

    // «Далее» — последняя остановка: Tab возвращает на первую.
    fireEvent.keyDown(document, { key: "Tab" });
    expect(skip).toHaveFocus();
    // Shift+Tab с первой — на последнюю.
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(next).toHaveFocus();
  });

  it("после закрытия фокус возвращается на элемент-инициатор", () => {
    const initiator = document.createElement("button");
    initiator.textContent = "Тур по продукту";
    document.body.appendChild(initiator);
    initiator.focus();
    expect(initiator).toHaveFocus();

    setState(STEPS);
    const view = render(<TourOverlay />);
    expect(screen.getByRole("button", { name: "Далее" })).toHaveFocus();

    setState(DONE);
    view.rerender(<TourOverlay />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(initiator).toHaveFocus();

    initiator.remove();
  });
});
