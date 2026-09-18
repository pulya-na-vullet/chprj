import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as api from "../../api/client";
import type { HubDocumentInfo, PlaybookInfo } from "../../api/types";
import { ConfirmDialog, Input } from "../../ui";
import { FileTypeIcon } from "../files/FileTypeIcon";

const ALLOWED = [".docx", ".pdf"];
const MAX_BYTES = 20 * 1024 * 1024;

export interface NewReviewStart {
  documentId: string;
  filename: string;
  playbookId: string;
  playbookName: string;
  role: string;
}

/** Форма «Новая проверка» (T-0048, спека §2): документ из библиотеки или
 * загрузка + плейбук + роль полем формы (чипы ролей плейбука или свой
 * вариант — без чат-диалога). Роль обязательна только для плейбуков,
 * которые её объявляют (playbook.roles непусто, договоры): без неё review-
 * путь задаёт вопрос в чате, что ломает запуск из раздела. Плейбуки без
 * ролей (документы сервиса) запускаются без роли (T-0070). */
export function NewReviewDialog({
  onStart,
  onClose,
  initialDocumentId = null,
}: {
  onStart: (args: NewReviewStart) => void;
  onClose: () => void;
  initialDocumentId?: string | null;
}) {
  const [docs, setDocs] = useState<HubDocumentInfo[] | null>(null);
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [docId, setDocId] = useState<string | null>(initialDocumentId);
  const [playbookId, setPlaybookId] = useState<string | null>(null);
  const [chipRole, setChipRole] = useState<string | null>(null);
  const [freeRole, setFreeRole] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([api.listDocuments(), api.listPlaybooks()])
      .then(([d, p]) => {
        setDocs(d);
        setPlaybooks(p);
      })
      .catch(() => setLoadError(true));
  }, []);

  // Свежезагруженный документ дозревает (processing → ready) — поллинг, как
  // в FilesView; без processing-документов таймер не живёт.
  const hasProcessing = !!docs?.some((d) => d.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = setInterval(async () => {
      try {
        setDocs(await api.listDocuments());
      } catch {
        /* transient — keep polling */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [hasProcessing]);

  const upload = async (file: File) => {
    const lower = file.name.toLowerCase();
    if (!ALLOWED.some((ext) => lower.endsWith(ext))) {
      setUploadError("Поддерживаются только файлы .docx и .pdf");
      return;
    }
    if (file.size > MAX_BYTES) {
      setUploadError("Файл больше 20 МБ");
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      const created = await api.uploadLibraryDocument(file);
      setDocs((prev) => [created, ...(prev ?? []).filter((d) => d.id !== created.id)]);
      setDocId(created.id);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Не удалось загрузить файл");
    } finally {
      setUploading(false);
    }
  };

  const playbook = playbooks?.find((p) => p.id === playbookId) ?? null;
  const role = freeRole.trim() || chipRole || "";
  const selectedDoc = docs?.find((d) => d.id === docId) ?? null;
  const needsRole = (playbook?.roles ?? []).length > 0;
  const ready = Boolean(selectedDoc && selectedDoc.status === "ready" && playbook && (!needsRole || role));

  const submit = () => {
    if (!selectedDoc || !playbook || (needsRole && !role)) return;
    onStart({
      documentId: selectedDoc.id,
      filename: selectedDoc.filename,
      playbookId: playbook.id,
      playbookName: playbook.name,
      role,
    });
  };

  return (
    <ConfirmDialog
      open
      title="Новая проверка"
      confirmLabel="Запустить"
      confirmDisabled={!ready}
      onConfirm={submit}
      onClose={onClose}
    >
      <>
        {loadError ? (
          <div className="nrd-error">Не удалось загрузить данные. Закройте окно и попробуйте ещё раз.</div>
        ) : (
          <div className="nrd">
            <div className="nrd-sec">
              <div className="nrd-label">
                Документ
                <input
                  ref={inputRef}
                  type="file"
                  accept=".docx,.pdf"
                  className="files-input"
                  aria-label="Загрузить документ"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  className="files-btn"
                  onClick={() => inputRef.current?.click()}
                  disabled={uploading}
                >
                  <Upload size={13} /> {uploading ? "Загрузка…" : "Загрузить"}
                </button>
              </div>
              {uploadError && <div className="nrd-error">{uploadError}</div>}
              <div className="nrd-list" role="radiogroup" aria-label="Документ">
                {docs === null && <div className="src-skel" />}
                {docs?.length === 0 && (
                  <div className="nrd-note">Библиотека пуста — загрузите документ.</div>
                )}
                {docs?.map((d) => (
                  <label key={d.id} className="nrd-row">
                    <input
                      type="radio"
                      name="nrd-doc"
                      checked={docId === d.id}
                      disabled={d.status !== "ready"}
                      onChange={() => setDocId(d.id)}
                    />
                    <FileTypeIcon parser={d.parser} />
                    <span className="nrd-name">{d.filename}</span>
                    {d.status !== "ready" && (
                      <span className="nrd-note">
                        {d.status === "processing" ? "обрабатывается…" : "ошибка"}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            <div className="nrd-sec">
              <div className="nrd-label">Плейбук</div>
              <div className="nrd-list" role="radiogroup" aria-label="Плейбук">
                {playbooks === null && <div className="src-skel" />}
                {playbooks?.map((p) => (
                  <label key={p.id} className="nrd-row">
                    <input
                      type="radio"
                      name="nrd-pb"
                      checked={playbookId === p.id}
                      onChange={() => {
                        setPlaybookId(p.id);
                        setChipRole(null);
                      }}
                    />
                    <span className="nrd-name">{p.name}</span>
                    <span className="nrd-note">{p.rules_count} правил</span>
                  </label>
                ))}
              </div>
            </div>

            {needsRole && (
              <div className="nrd-sec">
                <div className="nrd-label">Ваша роль по договору</div>
                {playbook && (playbook.roles ?? []).length > 0 && (
                  <div className="rvp-ask-opts">
                    {(playbook.roles ?? []).map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={
                          chipRole === r && !freeRole.trim()
                            ? "rvp-ask-opt rvp-ask-picked"
                            : "rvp-ask-opt"
                        }
                        onClick={() => setChipRole(r)}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                )}
                <Input
                  value={freeRole}
                  onChange={setFreeRole}
                  placeholder="Или напишите свою: например, Грузополучатель"
                  aria-label="Своя роль"
                />
              </div>
            )}
          </div>
        )}
      </>
    </ConfirmDialog>
  );
}
