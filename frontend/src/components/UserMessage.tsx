import { memo } from "react";
import type { Message } from "../api/types";
import { formatTimestamp } from "../util/format";
import { CopyButton } from "./CopyButton";

export const UserMessage = memo(function UserMessage({ message }: { message: Message }) {
  return (
    <div className="msg-user">
      <div className="bubble-user">{message.content}</div>
      <div className="msg-meta">
        <span className="msg-time">{formatTimestamp(message.created_at)}</span>
        <CopyButton text={message.content} label="Копировать запрос" />
      </div>
    </div>
  );
});
