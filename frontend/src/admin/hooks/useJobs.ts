import { useCallback, useEffect, useRef, useState } from "react";
import { listJobs } from "../api";
import type { JobOut } from "../types";

const POLL_MS = 1500;

/** Poll /admin/jobs while a job is running; fire onFinished when it stops. */
export function useJobs(onFinished: () => void) {
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const activeRef = useRef<string | null>(null);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  const refresh = useCallback(async () => {
    let data;
    try {
      data = await listJobs();
    } catch {
      return; // транзиентная ошибка — попробуем на следующем тике
    }
    setJobs(data.jobs);
    const active = data.jobs.find((j) => j.state === "running") ?? null;
    if (activeRef.current !== null && active === null) onFinishedRef.current();
    activeRef.current = active?.id ?? null;
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (activeRef.current !== null) void refresh();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const active = jobs.find((j) => j.state === "running") ?? null;
  return { jobs, active, refresh };
}
