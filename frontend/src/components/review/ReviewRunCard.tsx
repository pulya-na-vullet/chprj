import { PanelRight, RotateCcw } from "lucide-react";
import type { HubDocumentInfo, ReviewProgress, ReviewReport } from "../../api/types";
import { DocChip } from "./DocChip";
import { LEVEL_LABELS, LEVEL_ORDER, LevelDot } from "./levels";

// A playbook name is only known once the report itself has been produced
// (report.playbook_name) — the progress/failed cards title themselves off
// `playbookName`, which can be empty when the run was answered through a
// reloaded conversation's persisted `ask` (no label context survives that
// round-trip, see ChatContext.answerAsk). Falls back to a bare "Проверка"
// rather than a title with a dangling separator.
function runCardTitle(prefix: string, playbookName: string): string {
  return playbookName ? `${prefix} · ${playbookName}` : prefix;
}

type ReviewRunCardProps =
  | {
      state: "progress";
      playbookName: string;
      doc?: HubDocumentInfo;
      progress: ReviewProgress;
      role?: string | null;
    }
  | {
      state: "done";
      report: ReviewReport;
      doc?: HubDocumentInfo;
      onOpen: () => void;
    }
  | {
      state: "failed";
      playbookName: string;
      doc?: HubDocumentInfo;
      detail: string;
      onRetry: () => void;
      role?: string | null;
    };

export function ReviewRunCard(props: ReviewRunCardProps) {
  if (props.state === "progress") {
    const { playbookName, doc, progress, role } = props;
    const fraction = progress.total > 0 ? progress.index / progress.total : 0;
    return (
      <div className="rvc-run-card">
        <div className="rvc-run-card-t">{runCardTitle("Проверка", playbookName)}</div>
        <div className="rvc-run-card-s">
          <DocChip doc={doc} />
          {role && <span>вы — {role}</span>}
        </div>
        <div className="rvc-run-progress">
          <div className="rvc-run-progress-line">
            {progress.index} из {progress.total} · {progress.title}
          </div>
          <div
            className="rvc-progress-track"
            role="progressbar"
            aria-label="Прогресс проверки"
            aria-valuemin={0}
            aria-valuemax={progress.total}
            aria-valuenow={progress.index}
          >
            <div className="rvc-progress-fill" style={{ transform: `scaleX(${fraction})` }} />
          </div>
        </div>
      </div>
    );
  }

  if (props.state === "failed") {
    const { playbookName, doc, detail, onRetry, role } = props;
    return (
      <div className="rvc-run-card">
        <div className="rvc-run-card-t">{runCardTitle("Проверка не удалась", playbookName)}</div>
        <div className="rvc-run-card-s">
          <DocChip doc={doc} />
          {role && <span>вы — {role}</span>}
        </div>
        <div className="rvc-run-error">{detail}</div>
        <button type="button" className="rvc-retry-btn" onClick={onRetry}>
          <RotateCcw size={14} />
          Повторить проверку
        </button>
      </div>
    );
  }

  const { report, doc, onOpen } = props;
  const counts = LEVEL_ORDER.map((level) => ({
    level,
    label: LEVEL_LABELS[level],
    n: report.risks.filter((r) => r.level === level).length,
  })).filter((c) => c.n > 0);

  // T-0052: в done-карточке только чип файла — роль и время здесь дублируют
  // шапку панели и метку сообщения под карточкой (замечание клиента).
  return (
    <div className="rvc-run-card">
      <div className="rvc-run-card-t">Проверка завершена · {report.playbook_name}</div>
      <div className="rvc-run-card-s">
        <DocChip doc={doc} />
      </div>
      {counts.length > 0 && (
        <div className="rvc-run-counts">
          {counts.map((c) => (
            <span key={c.level} className="rvc-lvl">
              <LevelDot level={c.level} />
              {c.label} {c.n}
            </span>
          ))}
        </div>
      )}
      <div className="rvc-run-open">
        <button type="button" onClick={onOpen}>
          <PanelRight size={14} />
          Открыть отчёт
        </button>
      </div>
    </div>
  );
}
