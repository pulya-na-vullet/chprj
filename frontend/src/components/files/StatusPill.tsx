import type { HubDocumentInfo } from "../../api/types";

/** Статус документа пилюлей: цвета — семантические токены --ok/--warn/--danger,
 * у «обработки» крутится кольцо (замирает при prefers-reduced-motion). */
export function StatusPill({ status }: { status: HubDocumentInfo["status"] }) {
  if (status === "processing") {
    return (
      <span className="st-pill st-run">
        <i className="st-ring" aria-hidden="true" />
        обработка
      </span>
    );
  }
  if (status === "failed") return <span className="st-pill st-err">ошибка</span>;
  return <span className="st-pill st-ok">готов</span>;
}
