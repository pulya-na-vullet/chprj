import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { CitationChip } from "../components/CitationChip";

const citations = [
  {
    act_short_name: "ГК РФ",
    kind: "codex",
    number: "1477",
    title: "Право на товарный знак",
    full_text: "Текст статьи 1477 о товарном знаке.",
    score: 0.1,
  },
  {
    act_short_name: "ГК РФ",
    kind: "codex",
    number: "1481",
    title: "Свидетельство на товарный знак",
    full_text: "Текст статьи 1481 о свидетельстве.",
    score: 0.2,
  },
];

vi.mock("../components/CitationsContext", () => ({
  useCitations: () => citations,
}));

describe("CitationChip accessibility", () => {
  it("has button role and ARIA when interactive", () => {
    render(
      <CitationChip dataAct="ГК РФ" dataNumbers="1477">
        ст. 1477 ГК РФ
      </CitationChip>,
    );
    const chip = screen.getByRole("button", { name: /1477/ });
    expect(chip).toHaveAttribute("aria-haspopup", "dialog");
    expect(chip).toHaveAttribute("aria-expanded", "false");
  });

  it("opens on Enter and closes on Escape (returning focus to chip)", () => {
    render(
      <CitationChip dataAct="ГК РФ" dataNumbers="1477">
        ст. 1477 ГК РФ
      </CitationChip>,
    );
    const chip = screen.getByRole("button", { name: /1477/ });
    chip.focus();
    fireEvent.keyDown(chip, { key: "Enter" });
    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(chip).toHaveAttribute("aria-expanded", "false");
  });

  it("opens on Space", () => {
    render(
      <CitationChip dataAct="ГК РФ" dataNumbers="1477">
        ст. 1477 ГК РФ
      </CitationChip>,
    );
    const chip = screen.getByRole("button", { name: /1477/ });
    fireEvent.keyDown(chip, { key: " " });
    expect(chip).toHaveAttribute("aria-expanded", "true");
  });
});

// T-0102, пункт 7: раньше тесты только открывали диалог и не смотрели, ЧТО
// в нём. Из-за этого снятие сверки номера статьи оставляло 31 тест зелёным:
// чип показывал бы первую попавшуюся статью нужного акта — цитата ведёт не
// туда, куда обещает её текст.
describe("CitationChip matches the exact article", () => {
  it("shows the article named by the chip, not another one from the same act", () => {
    render(
      <CitationChip dataAct="ГК РФ" dataNumbers="1481">
        ст. 1481 ГК РФ
      </CitationChip>,
    );
    fireEvent.click(screen.getByRole("button", { name: /1481/ }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("ст. 1481 ГК РФ");
    expect(dialog).toHaveTextContent("Текст статьи 1481 о свидетельстве.");
    expect(dialog).not.toHaveTextContent("1477");
    expect(dialog).not.toHaveTextContent("Текст статьи 1477 о товарном знаке.");
  });

  it("renders a chip for several numbers with exactly those articles", () => {
    render(
      <CitationChip dataAct="ГК РФ" dataNumbers="1477,1481">
        ст. 1477, 1481 ГК РФ
      </CitationChip>,
    );
    fireEvent.click(screen.getByRole("button", { name: /1477/ }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Текст статьи 1477 о товарном знаке.");
    expect(dialog).toHaveTextContent("Текст статьи 1481 о свидетельстве.");
  });

  it("is inert when the cited number is not among the citations", () => {
    render(
      <CitationChip dataAct="ГК РФ" dataNumbers="9999">
        ст. 9999 ГК РФ
      </CitationChip>,
    );
    expect(screen.queryByRole("button")).toBeNull();
    fireEvent.click(screen.getByText("ст. 9999 ГК РФ"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is inert when the number matches but the act does not", () => {
    render(
      <CitationChip dataAct="НК РФ" dataNumbers="1477">
        ст. 1477 НК РФ
      </CitationChip>,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});
