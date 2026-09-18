import { UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { ApiError, uploadDocument } from "../api";
import type { LegalActKind } from "../types";
import { AdminModal } from "./AdminModal";

interface Props {
  onClose: () => void;
  onDone: (jobId: string | null) => void;
}

export function UploadModal({ onClose, onDone }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [codeId, setCodeId] = useState("");
  const [shortName, setShortName] = useState("");
  const [fullName, setFullName] = useState("");
  const [kind, setKind] = useState<LegalActKind>("federal_law");
  const [ingestNow, setIngestNow] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File | null) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".docx")) {
      setError("Нужен файл .docx");
      return;
    }
    setError(null);
    setFile(f);
    setShortName((cur) => cur || f.name.replace(/\.docx$/i, ""));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Выберите файл .docx");
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("code_id", codeId);
    form.append("short_name", shortName);
    form.append("full_name", fullName);
    form.append("kind", kind);
    form.append("ingest_now", String(ingestNow));
    try {
      const resp = await uploadDocument(form);
      onDone(resp.job_id ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "не удалось загрузить");
      setBusy(false);
    }
  };

  return (
    <AdminModal title="Добавить документ" onClose={onClose} closeOnBackdrop={!busy}>
      <form onSubmit={(e) => void submit(e)}>
          <div
            className={`dropzone ${dragOver ? "dropzone-active" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              pick(e.dataTransfer.files[0] ?? null);
            }}
          >
            <UploadCloud size={18} />
            <div>{file ? file.name : "Перетащите .docx или кликните для выбора"}</div>
            <input
              ref={inputRef}
              type="file"
              accept=".docx"
              hidden
              data-testid="file-input"
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="form-grid">
            <label>
              code_id
              <input value={codeId} onChange={(e) => setCodeId(e.target.value)} required />
            </label>
            <label>
              Короткое название
              <input value={shortName} onChange={(e) => setShortName(e.target.value)} required />
            </label>
            <label>
              Полное название
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            </label>
            <label>
              Тип
              <select value={kind} onChange={(e) => setKind(e.target.value as LegalActKind)}>
                <option value="federal_law">федеральный закон</option>
                <option value="codex">кодекс</option>
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={ingestNow}
                onChange={(e) => setIngestNow(e.target.checked)}
              />
              Запустить загрузку сразу
            </label>
          </div>
          {error && <p className="error-text">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="btn-primary" disabled={busy}>
              Создать
            </button>
          </div>
        </form>
    </AdminModal>
  );
}
