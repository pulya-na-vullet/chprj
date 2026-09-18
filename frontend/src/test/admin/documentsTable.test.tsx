import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { DocumentsTable } from "../../admin/components/DocumentsTable";
import type { AdminDocument } from "../../admin/types";

const doc = (over: Partial<AdminDocument>): AdminDocument => ({
  code_id: "ГК-1",
  source_doc_id: "gk-1",
  short_name: "ГК РФ",
  full_name: "Гражданский кодекс",
  kind: "codex",
  status: "ingested",
  file_path: "documents/codecs/gk1.docx",
  file_exists: true,
  file_size: 1000,
  file_mtime: "2026-06-01T00:00:00Z",
  articles_count: 10,
  chunks_count: 40,
  ingested_at: "2026-06-02T00:00:00Z",
  ...over,
});

const docs = [
  doc({}),
  doc({ code_id: "44-ФЗ", source_doc_id: "44-fz", short_name: "44-ФЗ",
        full_name: "О контрактной системе", kind: "federal_law", status: "not_ingested",
        articles_count: null, chunks_count: null, ingested_at: null }),
];

it("filters by text", () => {
  render(
    <DocumentsTable documents={docs} totalChunks={40} dbSize={12_582_912} jobRunning={false}
      onSelect={vi.fn()} onIngest={vi.fn()} onDelete={vi.fn()} />,
  );
  expect(screen.getByText("ГК РФ")).toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText("Фильтр по названию…"), {
    target: { value: "контрактной" },
  });
  expect(screen.queryByText("ГК РФ")).not.toBeInTheDocument();
  expect(screen.getByText("44-ФЗ")).toBeInTheDocument();
});

it("shows status badges and disables ingest while a job runs", () => {
  render(
    <DocumentsTable documents={docs} totalChunks={40} dbSize={12_582_912} jobRunning={true}
      onSelect={vi.fn()} onIngest={vi.fn()} onDelete={vi.fn()} />,
  );
  expect(screen.getByText("загружен")).toBeInTheDocument();
  expect(screen.getByText("не загружен")).toBeInTheDocument();
  expect(screen.getByTitle("Загрузить")).toBeDisabled();
});

it("row click selects, action click does not bubble", () => {
  const onSelect = vi.fn();
  const onDelete = vi.fn();
  render(
    <DocumentsTable documents={[docs[0]]} totalChunks={40} dbSize={12_582_912} jobRunning={false}
      onSelect={onSelect} onIngest={vi.fn()} onDelete={onDelete} />,
  );
  fireEvent.click(screen.getAllByTitle("Удалить")[0]);
  expect(onDelete).toHaveBeenCalledTimes(1);
  expect(onSelect).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("ГК РФ"));
  expect(onSelect).toHaveBeenCalledTimes(1);
});
