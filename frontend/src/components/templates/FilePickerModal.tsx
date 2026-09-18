import { useEffect, useMemo, useState } from "react";
import * as api from "../../api/client";
import type { HubDocumentInfo } from "../../api/types";
import { ConfirmDialog, Input } from "../../ui";
import { FileTypeIcon } from "../files/FileTypeIcon";
import { formatDate } from "../files/format";

/** Пикер «Из моих файлов» (E20, flow-full шаг 4): компактный список
 * библиотеки с «Сутью» и датой. Единый компонент для двух входов — меню
 * скрепки и ask-кнопка агента; a11y (фокус-трап, Esc, aria) даёт
 * ConfirmDialog поверх core-components ModalDesktop. */
export function FilePickerModal({
  onClose,
  onPick,
}: {
  onClose: () => void;
  /** Вызывается с выбранным документом после «Приложить». */
  onPick: (doc: HubDocumentInfo) => void;
}) {
  const [docs, setDocs] = useState<HubDocumentInfo[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [query, setQuery] = useState("");
  const [pickedId, setPickedId] = useState<string | null>(null);

  useEffect(() => {
    api
      .listDocuments()
      .then(setDocs)
      .catch(() => setLoadError(true));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const ready = (docs ?? []).filter((d) => d.status === "ready");
    if (!q) return ready;
    return ready.filter(
      (d) =>
        d.filename.toLowerCase().includes(q) || (d.summary ?? "").toLowerCase().includes(q),
    );
  }, [docs, query]);

  const picked = filtered.find((d) => d.id === pickedId) ?? null;

  return (
    <ConfirmDialog
      open
      title="Из моих файлов"
      confirmLabel="Приложить"
      confirmDisabled={!picked}
      onConfirm={() => {
        if (picked) onPick(picked);
      }}
      onClose={onClose}
    >
      {loadError ? (
        <div className="fpk-note">Не удалось загрузить библиотеку. Попробуйте ещё раз.</div>
      ) : (
        <div className="fpk">
          <Input
            value={query}
            onChange={setQuery}
            placeholder="Поиск по файлам"
            aria-label="Поиск по файлам"
          />
          <div className="fpk-list" role="radiogroup" aria-label="Документ из библиотеки">
            {docs === null && <div className="src-skel" />}
            {docs !== null && filtered.length === 0 && (
              <div className="fpk-note">
                {query.trim() ? "Ничего не нашлось" : "В библиотеке пока нет готовых документов"}
              </div>
            )}
            {filtered.map((d) => (
              <label key={d.id} className={pickedId === d.id ? "fpk-row fpk-row-on" : "fpk-row"}>
                <input
                  type="radio"
                  name="fpk-doc"
                  className="fpk-radio"
                  checked={pickedId === d.id}
                  onChange={() => setPickedId(d.id)}
                />
                <FileTypeIcon parser={d.parser} />
                <span className="fpk-text">
                  <span className="fpk-name">{d.filename}</span>
                  {d.summary && <span className="fpk-su">{d.summary}</span>}
                </span>
                <span className="fpk-dt">{formatDate(d.created_at)}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </ConfirmDialog>
  );
}
