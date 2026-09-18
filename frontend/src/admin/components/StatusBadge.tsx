import { CircleAlert, CircleCheck, CircleDashed, Loader2, TriangleAlert } from "lucide-react";
import type { DocumentStatus } from "../types";

const MAP: Record<DocumentStatus, { Icon: typeof CircleCheck; label: string; cls: string }> = {
  ingested: { Icon: CircleCheck, label: "загружен", cls: "status-ok" },
  not_ingested: { Icon: CircleDashed, label: "не загружен", cls: "status-muted" },
  stale: { Icon: TriangleAlert, label: "файл новее БД", cls: "status-warn" },
  ingesting: { Icon: Loader2, label: "идёт загрузка", cls: "status-busy" },
  orphaned: { Icon: CircleAlert, label: "нет в манифесте", cls: "status-warn" },
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const { Icon, label, cls } = MAP[status];
  return (
    <span className={`status-badge ${cls}`}>
      <Icon size={14} className={status === "ingesting" ? "spin" : undefined} />
      {label}
    </span>
  );
}
