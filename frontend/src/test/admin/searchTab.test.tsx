import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SearchTab } from "../../admin/components/SearchTab";
import type { AdminDocument } from "../../admin/types";

const jsonResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

const docs = [
  { short_name: "ГК РФ", status: "ingested" },
  { short_name: "УК РФ", status: "not_ingested" },
] as AdminDocument[];

afterEach(() => vi.unstubAllGlobals());

it("runs a search with selected act filter and shows scored results", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    jsonResponse({
      articles: [
        {
          article_id: "a1",
          act_short_name: "ГК РФ",
          act_kind: "codex",
          number: "421",
          title: "Свобода договора",
          full_text: "...",
          score: 0.0312,
          matched_chunks: [
            { chunk_id: "c1", path: "ст. 421 ч. 1 ГК РФ", text: "текст чанка", score: 0.016 },
          ],
        },
      ],
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<SearchTab documents={docs} />);

  // только загруженные акты попадают в чипсы
  expect(screen.getByRole("button", { name: "ГК РФ" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "УК РФ" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "ГК РФ" }));
  fireEvent.change(screen.getByPlaceholderText(/Тестовый запрос/), {
    target: { value: "свобода договора" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Искать/ }));

  await waitFor(() => expect(screen.getByText(/Свобода договора/)).toBeInTheDocument());
  expect(screen.getByText(/RRF 0.0312/)).toBeInTheDocument();
  const url = String(fetchMock.mock.calls[0][0]);
  expect(url).toContain("/search?");
  expect(url).toContain("q=%D1%81%D0%B2%D0%BE%D0%B1");
  expect(url).toContain("acts=");
});
