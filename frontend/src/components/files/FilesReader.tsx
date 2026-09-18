import { ChevronsRight, ExternalLink, MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as api from "../../api/client";
import type { HubDocumentContent, HubDocumentInfo } from "../../api/types";
import { IconButton } from "../../ui";
import { humanizeDocError } from "./format";

function normalizeLine(line: string): string {
  return line
    .replace(/\s+/g, " ")
    .replace(/[.\s]+$/, "")
    .trim()
    .toLowerCase();
}

// Заголовок секции для читалки. Служебные id пайплайна («preamble»,
// «trailing» — латиница без цифр, приходят и в number, и в title)
// заголовками не являются и не показываются.
function sectionHeader(s: { number?: string | null; title?: string | null }): string | null {
  const parts = [s.number, s.title]
    .map((p) => (p ?? "").trim())
    .filter((p) => p !== "" && /[А-ЯЁа-яё0-9]/.test(p));
  return parts.length ? parts.join(". ") : null;
}

// Извлечённый текст секции часто начинается с той же строки, что и её
// заголовок, — дубль опускаем, чтобы заголовок не печатался дважды.
function paragraphs(text: string, skipHeads: (string | null)[] = []) {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const skip = new Set(skipHeads.filter(Boolean).map((h) => normalizeLine(h as string)));
  let start = 0;
  while (start < lines.length && skip.has(normalizeLine(lines[start]))) start += 1;
  return lines.slice(start).map((l, i) => <p key={i}>{l}</p>);
}

/** Содержимое слайд-панели читалки: шапка с действиями и телом документа. */
export function FilesReader({
  document: doc,
  onClose,
  onDelete,
}: {
  document: HubDocumentInfo;
  onClose: () => void;
  onDelete: () => void;
}) {
  const [content, setContent] = useState<HubDocumentContent | null>(null);
  const [contentError, setContentError] = useState(false);
  const [reload, setReload] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isPdf = doc.parser === "pdf";
  const isDocx = doc.parser === "docx";
  const downloadUrl = api.documentDownloadUrl(doc.id);

  // Fetch extracted text only for a ready docx — a PDF renders from the
  // original bytes via the iframe, and non-ready docs have no content yet.
  useEffect(() => {
    if (doc.status !== "ready" || !isDocx) return;
    let live = true;
    setContent(null);
    setContentError(false);
    api
      .getDocumentContent(doc.id)
      .then((c) => live && setContent(c))
      .catch(() => live && setContentError(true));
    return () => {
      live = false;
    };
  }, [doc.id, doc.status, isDocx, reload]);

  // Close on outside click / Escape, mirroring DocumentChip's menu behaviour.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  return (
    <>
      <div className="files-reader-head">
        <span className="files-reader-name" title={doc.filename}>
          {doc.filename}
        </span>
        <div className="files-reader-actions">
          <a className="files-btn" href={downloadUrl} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={13} /> Открыть оригинал
          </a>
          <div className="files-menu-wrap" ref={menuRef}>
            <IconButton
              view="transparent"
              size={24}
              icon={<MoreHorizontal size={15} />}
              aria-label="Ещё действия"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            />
            {menuOpen && (
              <div className="files-menu" role="menu">
                <a
                  className="files-menu-item"
                  role="menuitem"
                  href={downloadUrl}
                  onClick={() => setMenuOpen(false)}
                >
                  Скачать
                </a>
                <button
                  type="button"
                  className="files-menu-item"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    onDelete();
                  }}
                >
                  Удалить
                </button>
              </div>
            )}
          </div>
          <IconButton
            view="transparent"
            size={24}
            icon={<ChevronsRight size={15} />}
            aria-label="Закрыть документ"
            onClick={onClose}
          />
        </div>
      </div>
      <div className="files-reader-body">
        {doc.status === "processing" ? (
          <div className="src-state">Документ ещё обрабатывается…</div>
        ) : doc.status === "failed" ? (
          <div className="src-state">{humanizeDocError(doc.error)}</div>
        ) : isPdf ? (
          <iframe className="files-pdf" src={downloadUrl} title={doc.filename} />
        ) : contentError ? (
          <div className="src-state">
            Не удалось загрузить документ.
            <br />
            <button type="button" onClick={() => setReload((n) => n + 1)}>
              Повторить
            </button>
          </div>
        ) : content === null ? (
          <div className="files-doctext">
            <div className="src-skel" />
            <div className="src-skel" />
            <div className="src-skel" />
          </div>
        ) : (
          <div className="files-doctext">
            {content.sections.length > 0
              ? content.sections.map((s, i) => {
                  const header = sectionHeader(s);
                  return (
                    <div key={i} className="files-section">
                      {header && <div className="files-section-h">{header}</div>}
                      {paragraphs(s.text, [header, s.title ?? null])}
                    </div>
                  );
                })
              : paragraphs(content.full_text)}
          </div>
        )}
      </div>
    </>
  );
}
