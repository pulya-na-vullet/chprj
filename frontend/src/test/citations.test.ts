import { describe, expect, it } from "vitest";
import { findCitations } from "../markdown/citations";

const ACTS = ["ГК РФ", "КоАП РФ"];

describe("findCitations", () => {
  it("finds a single citation", () => {
    const m = findCitations("Согласно ст. 1477 ГК РФ, знак…", ACTS);
    expect(m).toHaveLength(1);
    expect(m[0].act).toBe("ГК РФ");
    expect(m[0].numbers).toEqual(["1477"]);
    expect(m[0].raw).toBe("ст. 1477 ГК РФ");
  });

  it("parses multiple numbers", () => {
    const m = findCitations("см. ст. 1477, 1481 ГК РФ.", ACTS);
    expect(m[0].numbers).toEqual(["1477", "1481"]);
  });

  it("handles dotted/КоАП-style numbers", () => {
    const m = findCitations("ст. 14.1.1-1 КоАП РФ", ACTS);
    expect(m[0].numbers).toEqual(["14.1.1-1"]);
    expect(m[0].act).toBe("КоАП РФ");
  });

  it("ignores acts not in the catalog", () => {
    expect(findCitations("ст. 5 ТК РФ", ACTS)).toEqual([]);
  });
});
