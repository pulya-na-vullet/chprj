import { describe, expect, it } from "vitest";
import { displayLabel, selectionToRequestActs, toggleSource } from "../state/sources";

const ALL = ["ГК РФ", "КоАП РФ", "ТК РФ"];

describe("source selection", () => {
  it("all selected → null (no filter sent)", () => {
    expect(selectionToRequestActs(ALL, ALL)).toBeNull();
  });

  it("subset selected → that subset", () => {
    expect(selectionToRequestActs(["ГК РФ"], ALL)).toEqual(["ГК РФ"]);
  });

  it("none selected → null (treated as no filter)", () => {
    expect(selectionToRequestActs([], ALL)).toBeNull();
  });

  it("toggle removes a selected source", () => {
    expect(toggleSource(["ГК РФ", "ТК РФ"], "ГК РФ")).toEqual(["ТК РФ"]);
  });

  it("toggle adds an unselected source", () => {
    expect(toggleSource(["ГК РФ"], "ТК РФ")).toEqual(["ГК РФ", "ТК РФ"]);
  });
});

describe("displayLabel", () => {
  it("returns 'Все' when none selected (we treat empty as no filter)", () => {
    expect(displayLabel([], ALL)).toBe("Все");
  });
  it("returns 'Все' when all selected", () => {
    expect(displayLabel(ALL, ALL)).toBe("Все");
  });
  it("returns count when a strict subset is selected", () => {
    expect(displayLabel(["ГК РФ"], ALL)).toBe("1");
  });
  it("returns 'Все' when total is 0 (no acts loaded yet)", () => {
    expect(displayLabel([], [])).toBe("Все");
  });
});
