import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useJobs } from "../../admin/hooks/useJobs";
import type { JobOut } from "../../admin/types";

const jsonResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

const running: JobOut = {
  id: "j1",
  code_id: "ГК",
  state: "running",
  stage: "embedding",
  progress_done: 1,
  progress_total: 4,
  started_at: "2026-06-12T10:00:00Z",
  finished_at: null,
  error: null,
  articles_count: null,
  chunks_count: null,
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("polls while a job runs, fires onFinished once, then stops polling", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse({ jobs: [running] }))
    .mockResolvedValue(jsonResponse({ jobs: [{ ...running, state: "succeeded" }] }));
  vi.stubGlobal("fetch", fetchMock);
  const onFinished = vi.fn();

  const { result } = renderHook(() => useJobs(onFinished));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(result.current.active?.id).toBe("j1");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1500);
  });
  expect(onFinished).toHaveBeenCalledTimes(1);
  expect(result.current.active).toBeNull();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(4500);
  });
  expect(fetchMock).toHaveBeenCalledTimes(2); // активного нет — поллинг молчит
});
