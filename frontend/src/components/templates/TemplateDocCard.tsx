import { documentDownloadUrl } from "../../api/client";
import type { DocumentReadyData } from "../../api/types";
import { pluralRu } from "../../util/format";
import { FileTypeIcon } from "../files/FileTypeIcon";

/** Карточка готового документа (E20, flow-full шаг 7): DOCX-иконка как в
 * «Файлах», «Скачать» — единственный красный акцент, «Открыть» ведёт в
 * читалку «Файлов». Живёт на сообщении (message.template_doc). */
export function TemplateDocCard({
  data,
  onOpen,
}: {
  data: DocumentReadyData;
  onOpen?: (documentId: string) => void;
}) {
  const filled = data.fields_filled;
  return (
    <div className="tpldoc">
      <FileTypeIcon parser="docx" />
      <div className="tpldoc-info">
        <div className="tpldoc-name">{data.filename}</div>
        <div className="tpldoc-sub">
          {filled} {pluralRu(filled, ["поле заполнено", "поля заполнено", "полей заполнено"])} ·
          сохранён в «Файлы»
        </div>
      </div>
      <div className="tpldoc-acts">
        <a
          className="tpldoc-btn tpldoc-btn-main"
          href={documentDownloadUrl(data.document_id)}
          download
        >
          Скачать
        </a>
        <button
          type="button"
          className="tpldoc-btn tpldoc-btn-quiet"
          onClick={() => onOpen?.(data.document_id)}
        >
          Открыть
        </button>
      </div>
    </div>
  );
}
