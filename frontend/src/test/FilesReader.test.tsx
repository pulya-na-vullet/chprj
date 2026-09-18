import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilesReader } from "../components/files/FilesReader";
import * as api from "../api/client";
import type { HubDocumentInfo } from "../api/types";

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1",
    owner_id: "default",
    filename: "Договор.pdf",
    content_type: "application/pdf",
    size: 2048,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    created_at: "2026-07-08T00:00:00Z",
    ...over,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("FilesReader", () => {
  it("renders a PDF as an iframe pointing at the download proxy", () => {
    const { container } = render(<FilesReader document={doc()} onClose={() => {}} onDelete={() => {}} />);
    const frame = container.querySelector("iframe.files-pdf") as HTMLIFrameElement | null;
    expect(frame).not.toBeNull();
    expect(frame?.getAttribute("src")).toBe("/documents/d1/download");
  });

  it("renders extracted sections for a docx", async () => {
    vi.spyOn(api, "getDocumentContent").mockResolvedValue({
      id: "d2",
      status: "ready",
      full_text: "полный текст",
      sections: [{ number: "1", title: "Предмет", text: "Тело статьи.", level: 1, start: 0, end: 1 }],
    });
    render(<FilesReader document={doc({ id: "d2", filename: "Устав.docx", parser: "docx" })} onClose={() => {}} onDelete={() => {}} />);
    expect(await screen.findByText("Тело статьи.")).toBeInTheDocument();
    expect(screen.getByText("1. Предмет")).toBeInTheDocument();
  });

  it("shows a processing notice for a not-yet-ready document", () => {
    render(<FilesReader document={doc({ status: "processing" })} onClose={() => {}} onDelete={() => {}} />);
    expect(screen.getByText(/обрабатывается/i)).toBeInTheDocument();
  });

  it("shows a failure notice for a failed document", () => {
    render(<FilesReader document={doc({ status: "failed", error: "битый zip" })} onClose={() => {}} onDelete={() => {}} />);
    expect(screen.getByText(/Не удалось обработать/i)).toBeInTheDocument();
  });

  it("shows a retry on content load error for a docx", async () => {
    vi.spyOn(api, "getDocumentContent").mockRejectedValue(new Error("boom"));
    render(<FilesReader document={doc({ id: "d3", filename: "Устав.docx", parser: "docx" })} onClose={() => {}} onDelete={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Не удалось загрузить/i)).toBeInTheDocument());
  });
});
