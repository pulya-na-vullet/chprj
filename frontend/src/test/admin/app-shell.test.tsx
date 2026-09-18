import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../../admin/App";

const jsonResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

const documents = [
  {
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
  },
];

function stubApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/admin/documents"))
        return jsonResponse({ documents, total_chunks: 40, db_size_bytes: 12_582_912 });
      if (url.startsWith("/admin/jobs")) return jsonResponse({ jobs: [] });
      if (url.startsWith("/admin/indexes")) return jsonResponse({ hnsw: true, gin: true });
      if (url.startsWith("/admin/agent/settings"))
        return jsonResponse({
          model: "qwen/qwen3.6-flash",
          generation: {},
          behavior: { max_tool_iterations: 4, tool_choice: "auto" },
          tools: {
            rag_search: { enabled: true, limit: 8, min_score: 0 },
            fetch_article: { enabled: true },
            list_acts: { enabled: true },
            date_calculator: { enabled: true },
            web_search: { enabled: false, max_results: 5 },
            web_fetch: { enabled: false, max_chars: 20000 },
          },
        });
      if (url.startsWith("/admin/agent/models")) return jsonResponse({ models: [] });
      if (url.startsWith("/admin/agent/defaults"))
        return jsonResponse({ system_prompt_legal: "L", system_prompt_text: "T" });
      if (url.startsWith("/admin/users")) return jsonResponse({ users: [] });
      if (url.startsWith("/healthz")) return jsonResponse({ status: "ok", db: "ok" });
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

it("loads documents, switches tabs, opens drawer on row click", async () => {
  stubApi();
  render(<App />);
  await waitFor(() => expect(screen.getByText("ГК РФ")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: /Поиск/ }));
  expect(screen.getByPlaceholderText(/Тестовый запрос/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Документы/ }));

  fireEvent.click(screen.getByText("ГК РФ"));
  await waitFor(() => expect(screen.getByText("Манифест")).toBeInTheDocument());
});

it("navigates between Источники and Агент sections", async () => {
  stubApi();
  render(<App />);
  await waitFor(() => expect(screen.getByText("ГК РФ")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: /Агент/ }));
  // Agent section renders its own sub-navigation (Модель / Поведение / Тулзы).
  await waitFor(() => expect(screen.getByRole("button", { name: /Тулзы/ })).toBeInTheDocument());
  expect(screen.queryByText("ГК РФ")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Источники/ }));
  await waitFor(() => expect(screen.getByText("ГК РФ")).toBeInTheDocument());
});

it("navigates to the Пользователи section", async () => {
  stubApi();
  render(<App />);
  await waitFor(() => expect(screen.getByText("ГК РФ")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: /Пользователи/ }));
  await waitFor(() => expect(screen.getByText("Пользователей пока нет")).toBeInTheDocument());
  expect(screen.queryByText("ГК РФ")).not.toBeInTheDocument();
});

it("opens the upload modal", async () => {
  stubApi();
  render(<App />);
  await waitFor(() => expect(screen.getByText("ГК РФ")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /Добавить документ/ }));
  expect(screen.getByRole("heading", { name: "Добавить документ" })).toBeInTheDocument();
});
