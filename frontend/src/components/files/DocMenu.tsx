import { MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { HubDocumentInfo } from "../../api/types";
import { IconButton } from "../../ui";

export interface DocMenuProps {
  doc: HubDocumentInfo;
  downloadUrl: string;
  onOpen: () => void;
  onAsk: () => void;
  onReview: () => void;
  onDelete: () => void;
}

// Приблизительная высота открытого меню (5 пунктов + разделитель + отступы) —
// используется, чтобы решить, влезает ли оно вниз, или его нужно перевернуть
// вверх (I4, финальное ревью: строка/карточка у нижнего края скролл-контейнера
// иначе обрезает меню).
const MENU_HEIGHT_ESTIMATE = 196;

/** Меню действий над документом. Живёт в строке таблицы и в карточке плитки,
 * поэтому гасит всплытие: клик по «···» не должен открывать читалку. */
export function DocMenu({ doc, downloadUrl, onOpen, onAsk, onReview, onDelete }: DocMenuProps) {
  const [open, setOpen] = useState(false);
  const [openUp, setOpenUp] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const ready = doc.status === "ready";

  // IconButton не обёрнут в forwardRef — фокус возвращаем через обёртку.
  const focusTrigger = () => wrapRef.current?.querySelector("button")?.focus();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Capture-фаза: слушатель на document срабатывает раньше любого
        // bubble-обработчика Esc выше по дереву (например, закрытия читалки в
        // FilesView, тоже висящего на document) — stopPropagation здесь
        // гасит нативное событие до него, поэтому Esc закрывает только
        // верхний слой — открытое меню (Minor 7, финальное ревью).
        e.stopPropagation();
        setOpen(false);
        focusTrigger();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const run = (fn: () => void, enabled = true) => () => {
    if (!enabled) return;
    setOpen(false);
    fn();
  };

  const toggleOpen = () => {
    if (open) {
      setOpen(false);
      return;
    }
    const el = wrapRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      const scrollParent = el.closest<HTMLElement>(".files-table, .files-grid");
      const bottomLimit = scrollParent
        ? scrollParent.getBoundingClientRect().bottom
        : window.innerHeight;
      setOpenUp(bottomLimit - rect.bottom < MENU_HEIGHT_ESTIMATE);
    }
    setOpen(true);
  };

  return (
    <div
      className="files-menu-wrap files-row-menu"
      ref={wrapRef}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <IconButton
        view="transparent"
        size={24}
        icon={<MoreHorizontal size={15} />}
        aria-label="Действия с документом"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggleOpen}
      />
      {open && (
        <div className={openUp ? "files-menu files-menu-up" : "files-menu"} role="menu">
          <button type="button" className="files-menu-item" role="menuitem" onClick={run(onOpen)}>
            Открыть
          </button>
          <button
            type="button"
            className={ready ? "files-menu-item" : "files-menu-item files-menu-item-off"}
            role="menuitem"
            aria-disabled={!ready}
            onClick={run(onAsk, ready)}
          >
            Спросить в чате
          </button>
          <button
            type="button"
            className={ready ? "files-menu-item" : "files-menu-item files-menu-item-off"}
            role="menuitem"
            aria-disabled={!ready}
            onClick={run(onReview, ready)}
          >
            Проверить на риски
          </button>
          <div className="files-menu-sep" role="separator" />
          <a
            className="files-menu-item"
            role="menuitem"
            href={downloadUrl}
            download={doc.filename}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setOpen(false)}
          >
            Скачать
          </a>
          <button
            type="button"
            className="files-menu-item files-menu-item-danger"
            role="menuitem"
            onClick={run(onDelete)}
          >
            Удалить
          </button>
        </div>
      )}
    </div>
  );
}
