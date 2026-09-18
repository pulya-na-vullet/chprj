import { History, Loader2, X } from "lucide-react";
import { useState } from "react";
import { cancelJob } from "../api";
import type { JobOut } from "../types";
import { formatDate } from "../util";

const STAGE_LABEL: Record<string, string> = {
  starting: "подготовка",
  acquiring: "чтение файла",
  parsing: "парсинг",
  chunking: "нарезка",
  embedding: "эмбеддинги",
  persisting: "запись в БД",
  indexing: "индексы",
};

const STATE_LABEL: Record<string, string> = {
  running: "выполняется",
  succeeded: "успех",
  failed: "ошибка",
  cancelled: "отменён",
};

interface Props {
  jobs: JobOut[];
  active: JobOut | null;
  onChanged: () => void;
}

export function JobBanner({ jobs, active, onChanged }: Props) {
  const [showHistory, setShowHistory] = useState(false);
  const history = jobs.filter((j) => j.state !== "running");

  return (
    <>
      {active && (
        <div className="job-banner" data-testid="job-banner">
          <Loader2 size={15} className="spin" />
          <b>Загрузка: {active.code_id}</b>
          <span>
            {STAGE_LABEL[active.stage] ?? active.stage}
            {active.progress_total > 0 ? ` · ${active.progress_done}/${active.progress_total}` : ""}
          </span>
          <div className="job-progress">
            <div
              className="job-progress-fill"
              style={{
                width:
                  active.progress_total > 0
                    ? `${(100 * active.progress_done) / active.progress_total}%`
                    : "8%",
              }}
            />
          </div>
          <button className="btn-ghost" onClick={() => void cancelJob(active.id).then(onChanged)}>
            <X size={14} /> Отменить
          </button>
        </div>
      )}
      {history.length > 0 && (
        <div className="job-history">
          <button className="btn-ghost" onClick={() => setShowHistory(!showHistory)}>
            <History size={13} /> история джобов ({history.length})
          </button>
          {showHistory && (
            <ul>
              {history.map((j) => (
                <li key={j.id}>
                  {formatDate(j.started_at)} · {j.code_id} · {STATE_LABEL[j.state] ?? j.state}
                  {j.state === "succeeded" && j.chunks_count != null
                    ? ` (${j.articles_count} статей, ${j.chunks_count} чанков)`
                    : ""}
                  {j.error ? <span className="job-error"> — {j.error}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
