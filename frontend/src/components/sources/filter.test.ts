import { describe, expect, it } from "vitest";
import type { Source } from "../../api/types";
import { baseFullName, collapseActs, partLabel } from "./filter";

const S = (over: Partial<Source>): Source => ({
  source_doc_id: "x",
  short_name: "ГК РФ",
  full_name: "Гражданский кодекс",
  kind: "codex",
  branch: "Гражданское право",
  redaction: null,
  status: "in_corpus",
  ...over,
});

describe("partLabel / baseFullName", () => {
  it("parses part labels", () => {
    expect(partLabel("Гражданский кодекс РФ (часть первая)")).toBe("ч. 1");
    expect(partLabel("Налоговый кодекс РФ (часть вторая)")).toBe("ч. 2");
    expect(partLabel("Трудовой кодекс РФ")).toBeNull();
  });

  it("strips the part suffix", () => {
    expect(baseFullName("Гражданский кодекс РФ (часть первая)")).toBe("Гражданский кодекс РФ");
  });
});

describe("collapseActs", () => {
  const data = [
    S({ source_doc_id: "gk2", short_name: "ГК РФ", full_name: "Гражданский кодекс РФ (часть вторая)" }),
    S({ source_doc_id: "gk1", short_name: "ГК РФ", full_name: "Гражданский кодекс РФ (часть первая)" }),
    S({ source_doc_id: "apk", short_name: "АПК РФ", full_name: "Арбитражный процессуальный кодекс", branch: "Арбитражный процесс" }),
    S({ source_doc_id: "fz44", short_name: "44-ФЗ", full_name: "О контрактной системе", kind: "federal_law", branch: "Закупки" }),
  ];

  it("collapses multi-part acts into one ordered entry", () => {
    const groups = collapseActs(data);
    const gk = groups.find((g) => g.short === "ГК РФ");
    expect(gk?.parts.map((p) => p.source_doc_id)).toEqual(["gk1", "gk2"]);
    expect(gk?.full).toBe("Гражданский кодекс РФ");
  });

  it("orders codices before federal laws, alphabetical within", () => {
    expect(collapseActs(data).map((g) => g.short)).toEqual(["АПК РФ", "ГК РФ", "44-ФЗ"]);
  });
});
