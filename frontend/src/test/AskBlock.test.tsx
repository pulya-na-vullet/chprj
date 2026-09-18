import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { AskBlock } from "../components/review/AskBlock";
import type { MessageAsk } from "../api/types";

function ask(over: Partial<MessageAsk> = {}): MessageAsk {
  return {
    kind: "review_role",
    template: false,
    question: "Кто вы по этому договору?",
    options: ["Покупатель", "Поставщик"],
    ...over,
  };
}

describe("AskBlock (T-0046)", () => {
  it("renders one pill button per option, plus a dashed free-text button", () => {
    render(<AskBlock ask={ask()} active onPick={vi.fn()} onFree={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Поставщик" })).toBeInTheDocument();
    const free = screen.getByRole("button", { name: "Другое — напишу сам" });
    expect(free).toBeInTheDocument();
    expect(free.className).toContain("rvp-ask-free");
  });

  it("does not render the question text itself (it's already in the message content)", () => {
    render(<AskBlock ask={ask()} active onPick={vi.fn()} onFree={vi.fn()} />);
    expect(screen.queryByText("Кто вы по этому договору?")).toBeNull();
  });

  it("shows the note about answering by text", () => {
    render(<AskBlock ask={ask()} active onPick={vi.fn()} onFree={vi.fn()} />);
    expect(screen.getByText("Можно ответить и текстом в поле ниже")).toBeInTheDocument();
  });

  it("clicking an option calls onPick with its text", () => {
    const onPick = vi.fn();
    render(<AskBlock ask={ask()} active onPick={onPick} onFree={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Покупатель" }));
    expect(onPick).toHaveBeenCalledWith("Покупатель");
  });

  it("clicking the free-text button calls onFree", () => {
    const onFree = vi.fn();
    render(<AskBlock ask={ask()} active onPick={vi.fn()} onFree={onFree} />);
    fireEvent.click(screen.getByRole("button", { name: "Другое — напишу сам" }));
    expect(onFree).toHaveBeenCalledTimes(1);
  });

  it("active=false disables every button (the conversation has moved on)", () => {
    render(<AskBlock ask={ask()} active={false} onPick={vi.fn()} onFree={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Поставщик" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Другое — напишу сам" })).toBeDisabled();
  });

  it("no options (playbook declares none) — only the free-text button renders", () => {
    render(<AskBlock ask={ask({ options: [] })} active onPick={vi.fn()} onFree={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Покупатель" })).toBeNull();
    expect(screen.getByRole("button", { name: "Другое — напишу сам" })).toBeInTheDocument();
  });
});
