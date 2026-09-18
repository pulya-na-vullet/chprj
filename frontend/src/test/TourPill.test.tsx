// Пилюля «Тур по продукту · N/4» (T-0132): метка, компактная форма в
// свёрнутом сайдбаре, искра-celebrate, перезапуск кликом, скрытие.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { TourPill } from "../components/tour/TourPill";

describe("TourPill (T-0132)", () => {
  it("полная форма: название и счётчик; клик перезапускает тур", () => {
    const onStart = vi.fn();
    render(<TourPill visible compact={false} label="2/4" celebrate={false} onStart={onStart} />);
    const pill = screen.getByRole("button", { name: /Тур по продукту/ });
    expect(pill).toHaveTextContent("2/4");
    fireEvent.click(pill);
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("компактная форма в свёрнутом сайдбаре — только счётчик", () => {
    render(<TourPill visible compact label="1/4" celebrate={false} onStart={vi.fn()} />);
    const pill = screen.getByRole("button", { name: /Тур по продукту/ });
    expect(pill).toHaveTextContent("1/4");
    expect(pill).not.toHaveTextContent("Тур по продукту 1/4");
  });

  it("celebrate вешает класс искры (два оборота задаёт CSS-анимация)", () => {
    render(<TourPill visible compact={false} label="4/4" celebrate onStart={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Тур по продукту/ })).toHaveClass(
      "tour-pill-celebrate",
    );
  });

  it("скрытая пилюля не рендерится вовсе", () => {
    render(<TourPill visible={false} compact={false} label="0/4" celebrate={false} onStart={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Тур по продукту/ })).not.toBeInTheDocument();
  });
});
