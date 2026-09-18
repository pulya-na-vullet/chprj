import type { HubDocumentInfo } from "../../api/types";
import { FileTypeIcon } from "./FileTypeIcon";
import { StatusPill } from "./StatusPill";
import { formatSize, shortDate, summaryLabel } from "./format";

/** Карточка плитки: тот же набор данных и та же логика выбора, что и строка
 * списка — включая чекбокс выбора (I1, финальное ревью): без него полоса
 * «Спросить по N документам» залипала в плитке, снять выбор было нечем.
 * Меню приходит готовым элементом — оно одно на оба вида. */
export function FileCard({
  doc,
  checked,
  onOpen,
  onToggleCheck,
  menu,
}: {
  doc: HubDocumentInfo;
  checked: boolean;
  onOpen: () => void;
  onToggleCheck: () => void;
  menu: React.ReactNode;
}) {
  return (
    <div
      className={checked ? "file-card file-card-on" : "file-card"}
      role="button"
      tabIndex={0}
      aria-label={doc.filename}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="file-card-top">
        <span
          role="checkbox"
          aria-checked={checked}
          aria-label={`Выбрать «${doc.filename}»`}
          aria-disabled={doc.status !== "ready"}
          tabIndex={doc.status === "ready" ? 0 : -1}
          className={
            doc.status !== "ready"
              ? "files-check files-check-off"
              : checked
                ? "files-check files-check-on"
                : "files-check"
          }
          onClick={(e) => {
            e.stopPropagation();
            onToggleCheck();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              onToggleCheck();
            }
          }}
        />
        <FileTypeIcon parser={doc.parser} />
        <span className="file-card-name" title={doc.filename}>
          {doc.filename}
        </span>
        {menu}
      </div>
      <div className={doc.status === "ready" ? "file-card-sum" : "file-card-sum file-card-sum-note"}>
        {summaryLabel(doc)}
      </div>
      <div className="file-card-foot">
        <StatusPill status={doc.status} />
        <span className="file-card-dim">
          {formatSize(doc.size)} · {shortDate(doc.created_at)}
        </span>
      </div>
    </div>
  );
}
