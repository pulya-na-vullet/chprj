import type { HubDocumentInfo } from "../../api/types";
import { ConfirmDialog } from "../../ui";

export function DeleteDialog({
  document: doc,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  document: HubDocumentInfo;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ConfirmDialog
      open
      title="Удалить документ?"
      confirmLabel="Удалить"
      busy={busy}
      error={error}
      onConfirm={onConfirm}
      onClose={onCancel}
    >
      «{doc.filename}» будет удалён безвозвратно, включая оригинал.
    </ConfirmDialog>
  );
}
