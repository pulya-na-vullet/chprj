import { describe, expect, it } from "vitest";
import { filterDocuments } from "../components/files/filter";
import { formatSize } from "../components/files/format";
import type { HubDocumentInfo } from "../api/types";

function doc(filename: string): HubDocumentInfo {
  return {
    id: filename,
    owner_id: "default",
    filename,
    content_type: "application/pdf",
    size: 1024,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    created_at: "2026-07-08T00:00:00Z",
  };
}

describe("filterDocuments", () => {
  const docs = [doc("Договор.pdf"), doc("Устав.docx"), doc("акт.pdf")];

  it("empty query returns all", () => {
    expect(filterDocuments(docs, "")).toHaveLength(3);
  });

  it("filters case-insensitively by filename", () => {
    expect(filterDocuments(docs, "устав").map((d) => d.filename)).toEqual(["Устав.docx"]);
  });

  it("trims whitespace-only query to all", () => {
    expect(filterDocuments(docs, "   ")).toHaveLength(3);
  });
});

describe("formatSize", () => {
  it("formats bytes below 1 KB", () => {
    expect(formatSize(512)).toBe("512 Б");
  });
  it("formats kilobytes", () => {
    expect(formatSize(2048)).toBe("2,0 КБ");
  });
  it("formats megabytes", () => {
    expect(formatSize(5 * 1024 * 1024)).toBe("5,0 МБ");
  });
});
