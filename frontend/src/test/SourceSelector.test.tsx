import { render, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { SourceSelector } from "../components/SourceSelector";

const setSelectedSources = vi.fn();

const state = {
  acts: ["ГК РФ", "ВК РФ", "129-ФЗ"],
  actsFull: [
    { short_name: "ГК РФ", full_name: "Гражданский кодекс РФ", kind: "codex" },
    { short_name: "ВК РФ", full_name: "Воздушный кодекс РФ", kind: "codex" },
    { short_name: "129-ФЗ", full_name: "ФЗ о госрегистрации", kind: "federal_law" },
  ],
  selectedSources: ["ГК РФ", "ВК РФ"],
  actsStatus: "ready" as const,
  actsError: null,
};

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({ state, setSelectedSources, retryActs: vi.fn() }),
}));

describe("SourceSelector (выбор группами, T-0057)", () => {
  beforeEach(() => setSelectedSources.mockClear());

  it("панель показывает группы; пустая «Судебная практика» недоступна", async () => {
    render(<SourceSelector />);
    fireEvent.click(screen.getByRole("button", { name: /Источники/ }));
    // Popover позиционируется через react-popper микротаском — ждём через findBy.
    expect(await screen.findByRole("button", { name: /Кодексы/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Федеральные законы/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Судебная практика/ })).toBeDisabled();
  });

  it("клик по невыбранной группе дозаполняет выбор её актами", async () => {
    render(<SourceSelector />);
    fireEvent.click(screen.getByRole("button", { name: /Источники/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Федеральные законы/ }));
    expect(setSelectedSources).toHaveBeenCalledWith(["ГК РФ", "ВК РФ", "129-ФЗ"]);
  });

  it("клик по полностью выбранной группе снимает её акты", async () => {
    render(<SourceSelector />);
    fireEvent.click(screen.getByRole("button", { name: /Источники/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Кодексы/ }));
    expect(setSelectedSources).toHaveBeenCalledWith([]);
  });
});
