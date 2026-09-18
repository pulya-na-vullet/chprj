import { useEffect, useId, useRef } from "react";

/** Shared modal shell for the admin app (T-0036 a11y).
 *
 * The admin dialogs used to hand-roll `.modal-overlay`/`.modal` with no dialog
 * semantics — screen readers didn't announce them and Esc didn't close them.
 * This wrapper adds `role="dialog"` + `aria-modal` + `aria-labelledby`, closes
 * on Escape, moves focus into the dialog on open, and restores it on close.
 * Backdrop-click close is opt-out (`closeOnBackdrop={false}` while a request is
 * in flight). Full Tab focus-trapping is intentionally left to a later
 * ui/ConfirmDialog migration; this is the meaningful minimum. */
export function AdminModal({
  title,
  onClose,
  closeOnBackdrop = true,
  children,
}: {
  title: string;
  onClose: () => void;
  closeOnBackdrop?: boolean;
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    // Don't steal focus from an autoFocus'd field already inside the dialog.
    if (dialogRef.current && !dialogRef.current.contains(prevFocus)) {
      dialogRef.current.focus();
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prevFocus?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={closeOnBackdrop ? onClose : undefined}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={titleId}>{title}</h3>
        {children}
      </div>
    </div>
  );
}
