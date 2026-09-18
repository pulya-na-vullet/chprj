import { ModalDesktop } from "@alfalab/core-components/modal/desktop";
import type { ReactNode } from "react";
import { Button } from "./Button";

/** Компактное подтверждение действия. Кнопка подтверждения — акцентная (деструктив).
 * `confirmDisabled` (T-0048) — для диалогов-форм, где подтверждение доступно
 * только после валидного выбора. */
export function ConfirmDialog({
  open,
  title,
  confirmLabel,
  onConfirm,
  onClose,
  children,
  busy = false,
  confirmDisabled = false,
  error,
}: {
  open: boolean;
  title: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  children?: ReactNode;
  busy?: boolean;
  confirmDisabled?: boolean;
  error?: string | null;
}) {
  return (
    <ModalDesktop open={open} onClose={onClose} size={500}>
      <ModalDesktop.Header hasCloser title={title} />
      {(children || error) && (
        <ModalDesktop.Content>
          {children}
          {error && <div className="confirm-dialog-error">{error}</div>}
        </ModalDesktop.Content>
      )}
      <ModalDesktop.Footer>
        <Button onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button view="accent" onClick={onConfirm} loading={busy} disabled={confirmDisabled}>
          {confirmLabel}
        </Button>
      </ModalDesktop.Footer>
    </ModalDesktop>
  );
}
