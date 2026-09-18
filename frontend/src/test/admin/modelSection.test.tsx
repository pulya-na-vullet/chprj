import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ModelSection } from "../../admin/components/agent/ModelSection";
import type { AgentSettings } from "../../admin/types";

const jsonResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

const settings = (over: Partial<AgentSettings> = {}): AgentSettings => ({
  model: "qwen/qwen3.6-flash",
  generation: {},
  behavior: { max_tool_iterations: 8, tool_choice: "auto" },
  review: {},
  tools: {
    date_calculator: { enabled: true },
    fetch_article: { enabled: true },
    list_acts: { enabled: true },
    rag_search: { enabled: true, limit: 8, min_score: 0 },
    web_fetch: { enabled: false, max_chars: 20000 },
    web_search: { enabled: false, max_results: 5 },
  },
  ...over,
});

/** Scope queries to the "Проверка договоров" card so they don't collide with
 * the unrelated OpenRouter catalog table / other selects in the section. */
const reviewCard = () => screen.getByText("Проверка договоров").closest(".agent-card") as HTMLElement;

afterEach(() => vi.unstubAllGlobals());

it("renders the review model + concurrency fields with defaults as placeholders", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse({ models: [{ id: "openai/gpt-4o-mini", name: "GPT-4o mini", supports_tools: true }] }),
    ),
  );
  render(
    <ModelSection value={settings({ review: { model: null, concurrency: null } })} onChange={vi.fn()} />,
  );

  const card = reviewCard();
  expect(within(card).getByText("По умолчанию (openai/gpt-4o-mini)")).toBeInTheDocument();

  const concurrencyInput = within(card).getByPlaceholderText("4");
  expect(concurrencyInput).toHaveValue(null);
  expect(concurrencyInput).toHaveAttribute("min", "1");
  expect(concurrencyInput).toHaveAttribute("max", "12");

  await waitFor(() => expect(within(card).getByText("GPT-4o mini")).toBeInTheDocument());
});

it("picking a review model calls onChange with review.model set", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse({ models: [{ id: "openai/gpt-4o-mini", name: "GPT-4o mini", supports_tools: true }] }),
    ),
  );
  const onChange = vi.fn();
  const value = settings({ review: { model: null, concurrency: null } });
  render(<ModelSection value={value} onChange={onChange} />);

  const card = reviewCard();
  await waitFor(() => expect(within(card).getByText("GPT-4o mini")).toBeInTheDocument());

  const modelSelect = within(card).getByRole("combobox");
  fireEvent.change(modelSelect, { target: { value: "openai/gpt-4o-mini" } });

  expect(onChange).toHaveBeenCalledWith({
    ...value,
    review: { model: "openai/gpt-4o-mini", concurrency: null },
  });
});

it("clearing the review model select falls back to null (default)", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse({ models: [{ id: "openai/gpt-4o-mini", name: "GPT-4o mini", supports_tools: true }] }),
    ),
  );
  const onChange = vi.fn();
  const value = settings({ review: { model: "openai/gpt-4o-mini", concurrency: 6 } });
  render(<ModelSection value={value} onChange={onChange} />);

  const card = reviewCard();
  await waitFor(() => expect(within(card).getByText("GPT-4o mini")).toBeInTheDocument());

  const modelSelect = within(card).getByRole("combobox");
  fireEvent.change(modelSelect, { target: { value: "" } });

  expect(onChange).toHaveBeenCalledWith({
    ...value,
    review: { model: null, concurrency: 6 },
  });
});

it("editing concurrency calls onChange with a number", async () => {
  const fetchMock = vi.fn(async () => jsonResponse({ models: [] }));
  vi.stubGlobal("fetch", fetchMock);
  const onChange = vi.fn();
  const value = settings({ review: { model: null, concurrency: null } });
  render(<ModelSection value={value} onChange={onChange} />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

  const concurrencyInput = within(reviewCard()).getByPlaceholderText("4");
  fireEvent.change(concurrencyInput, { target: { value: "6" } });
  expect(onChange).toHaveBeenLastCalledWith({
    ...value,
    review: { model: null, concurrency: 6 },
  });
});

it("clearing concurrency calls onChange with null (falls back to the default)", async () => {
  const fetchMock = vi.fn(async () => jsonResponse({ models: [] }));
  vi.stubGlobal("fetch", fetchMock);
  const onChange = vi.fn();
  const value = settings({ review: { model: null, concurrency: 6 } });
  render(<ModelSection value={value} onChange={onChange} />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

  const concurrencyInput = within(reviewCard()).getByPlaceholderText("4");
  fireEvent.change(concurrencyInput, { target: { value: "" } });
  expect(onChange).toHaveBeenLastCalledWith({
    ...value,
    review: { model: null, concurrency: null },
  });
});
