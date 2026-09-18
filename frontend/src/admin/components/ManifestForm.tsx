import { useState } from "react";
import { ApiError, updateManifest } from "../api";
import type { AdminDocument, LegalActKind } from "../types";

interface Props {
  doc: AdminDocument;
  onSaved: () => void;
}

export function ManifestForm({ doc, onSaved }: Props) {
  const [shortName, setShortName] = useState(doc.short_name);
  const [fullName, setFullName] = useState(doc.full_name);
  const [kind, setKind] = useState<LegalActKind>(doc.kind);
  const [docxPath, setDocxPath] = useState(doc.file_path ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const codeId = doc.code_id;
  if (!codeId) {
    return <p className="empty-state">Записи манифеста нет (документ только в БД).</p>;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateManifest(codeId, {
        short_name: shortName,
        full_name: fullName,
        kind,
        docx_path: docxPath,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="form-grid" onSubmit={(e) => void submit(e)}>
      <label>
        code_id
        <input value={codeId} disabled />
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
          <option value="codex">кодекс</option>
          <option value="federal_law">федеральный закон</option>
        </select>
      </label>
      <label>
        Путь к .docx
        <input value={docxPath} onChange={(e) => setDocxPath(e.target.value)} required />
      </label>
      <div>
        <button className="btn-primary" type="submit" disabled={saving}>
          Сохранить
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </form>
  );
}
