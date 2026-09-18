import { useState } from "react";
import type { AdminDocument, DeleteDocumentRequest } from "../types";
import { AdminModal } from "./AdminModal";

interface Props {
  doc: AdminDocument;
  onClose: () => void;
  onConfirm: (opts: DeleteDocumentRequest) => void;
}

export function DeleteDialog({ doc, onClose, onConfirm }: Props) {
  const [dropManifest, setDropManifest] = useState(false);
  const [dropFile, setDropFile] = useState(false);
  const hasManifest = doc.code_id !== null;

  return (
    <AdminModal title={`Удалить «${doc.short_name}» из БД?`} onClose={onClose}>
      <p className="modal-text">
        Из базы будут удалены {doc.articles_count ?? 0} статей и {doc.chunks_count ?? 0} чанков.
        Файл и запись манифеста останутся, если не отмечено иное.
      </p>
      <label className="checkbox-row">
          <input
            type="checkbox"
            checked={dropManifest}
            disabled={!hasManifest}
            onChange={(e) => setDropManifest(e.target.checked)}
          />
          также удалить запись из manifest.yaml
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={dropFile}
            disabled={!hasManifest || !doc.file_exists}
            onChange={(e) => setDropFile(e.target.checked)}
          />
          также удалить .docx с диска
        </label>
      <div className="modal-actions">
        <button className="btn-ghost" onClick={onClose}>
          Отмена
        </button>
        <button
          className="btn-primary"
          onClick={() => onConfirm({ drop_manifest: dropManifest, drop_file: dropFile })}
        >
          Удалить
        </button>
      </div>
    </AdminModal>
  );
}
