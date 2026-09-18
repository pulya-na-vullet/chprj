import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import type { Conversation } from "../api/types";
import { ConfirmDialog, IconButton } from "../ui";

export function ConversationItem({
  conv,
  active,
  onOpen,
  onDelete,
}: {
  conv: Conversation;
  active: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <>
      <div className={active ? "conv-item conv-item-active" : "conv-item"} onClick={onOpen}>
        <span className="conv-title">{conv.title}</span>
        <IconButton
          className="conv-delete"
          view="transparent"
          size={24}
          icon={<MoreHorizontal size={15} />}
          aria-label="Удалить задачу"
          onClick={(e) => {
            e.stopPropagation();
            setConfirming(true);
          }}
        />
      </div>
      {/* Диалог вне кликабельной карточки: модалка живёт в DOM-портале, но
          React всплывает синтетические события по дереву КОМПОНЕНТОВ, поэтому
          внутри <div onClick={onOpen}> клики по кнопкам диалога стреляли в onOpen */}
      <ConfirmDialog
        open={confirming}
        title="Удалить задачу?"
        confirmLabel="Удалить"
        onConfirm={() => {
          setConfirming(false);
          onDelete();
        }}
        onClose={() => setConfirming(false)}
      />
    </>
  );
}
