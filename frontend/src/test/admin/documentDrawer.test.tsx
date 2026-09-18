import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DocumentDrawer } from "../../admin/components/DocumentDrawer";
import type { AdminDocument } from "../../admin/types";

const doc: AdminDocument = {
  code_id: "ГК-1",
  source_doc_id: "gk-1",
  short_name: "ГК РФ",
  full_name: "Гражданский кодекс",
  kind: "codex",
  status: "ingested",
  file_path: "documents/codecs/gk1.docx",
  file_exists: true,
  file_size: 2_100_000,
  file_mtime: "2026-06-01T00:00:00Z",
  articles_count: 10,
  chunks_count: 40,
  ingested_at: "2026-06-02T00:00:00Z",
};

const jsonResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

afterEach(() => vi.unstubAllGlobals());

it("shows overview and switches to articles tab (loads list)", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    jsonResponse({
      articles: [{ article_id: "a1", number: "421", title: "Свобода договора", chunks_count: 3 }],
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <DocumentDrawer doc={doc} jobRunning={false} onClose={vi.fn()}
      onIngest={vi.fn()} onDelete={vi.fn()} onManifestSaved={vi.fn()} />,
  );
  expect(screen.getByText("documents/codecs/gk1.docx")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Статьи" }));
  await waitFor(() => expect(screen.getByText(/Свобода договора/)).toBeInTheDocument());
  expect(fetchMock).toHaveBeenCalledWith(
    "/admin/documents/%D0%93%D0%9A-1/articles",
    undefined,
  );
});

it("manifest tab saves via PUT", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
  vi.stubGlobal("fetch", fetchMock);
  const onSaved = vi.fn();
  render(
    <DocumentDrawer doc={doc} jobRunning={false} onClose={vi.fn()}
      onIngest={vi.fn()} onDelete={vi.fn()} onManifestSaved={onSaved} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Манифест" }));
  fireEvent.change(screen.getByLabelText("Короткое название"), {
    target: { value: "ГК РФ (нов.)" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/admin/documents/%D0%93%D0%9A-1/manifest");
  expect(init.method).toBe("PUT");
  expect(JSON.parse(String(init.body)).short_name).toBe("ГК РФ (нов.)");
});
