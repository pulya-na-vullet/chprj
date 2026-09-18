import type { HubDocumentInfo } from "../../api/types";
import { FileTypeIcon } from "../files/FileTypeIcon";

/** Небольшой файловый чип (иконка типа + имя файла) — общий для карточки хода
 * проверки (ReviewRunCard) и панели отчёта (ReviewPanel), T-0010. */
export function DocChip({ doc }: { doc: HubDocumentInfo | undefined }) {
  if (!doc) return null;
  return (
    <span className="rvc-chip">
      <FileTypeIcon parser={doc.filename.toLowerCase().endsWith(".pdf") ? "pdf" : "docx"} />
      <span className="rvc-chip-name">{doc.filename}</span>
    </span>
  );
}
