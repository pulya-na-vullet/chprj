import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { JobBanner } from "../../admin/components/JobBanner";
import type { JobOut } from "../../admin/types";

const job = (over: Partial<JobOut>): JobOut => ({
  id: "j1",
  code_id: "ГК",
  state: "running",
  stage: "embedding",
  progress_done: 12,
  progress_total: 40,
  started_at: "2026-06-12T10:00:00Z",
  finished_at: null,
  error: null,
  articles_count: null,
  chunks_count: null,
  ...over,
});

it("renders active job with stage and progress", () => {
  render(<JobBanner jobs={[job({})]} active={job({})} onChanged={vi.fn()} />);
  expect(screen.getByText("Загрузка: ГК")).toBeInTheDocument();
  expect(screen.getByText(/эмбеддинги · 12\/40/)).toBeInTheDocument();
});

it("hides banner when idle and shows history with errors", () => {
  const failed = job({ id: "j2", state: "failed", error: "embedding: boom" });
  render(<JobBanner jobs={[failed]} active={null} onChanged={vi.fn()} />);
  expect(screen.queryByTestId("job-banner")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /история джобов/ }));
  expect(screen.getByText(/embedding: boom/)).toBeInTheDocument();
});
