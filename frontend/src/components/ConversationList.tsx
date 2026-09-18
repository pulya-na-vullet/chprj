import { useChat } from "../state/ChatContext";
import { groupConversationsByTime } from "../state/conversationGroups";
import { Skeleton } from "../ui";
import { ConversationItem } from "./ConversationItem";

export function ConversationList() {
  const { state, openConversation, removeConversation, retryConversations } = useChat();

  if (state.conversationsStatus === "loading" && state.conversations.length === 0) {
    return (
      <div className="conv-list" role="status" aria-label="Загружаю историю">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} visible>
            <div className="conv-skeleton-row" />
          </Skeleton>
        ))}
      </div>
    );
  }
  if (state.conversationsStatus === "error" && state.conversations.length === 0) {
    return (
      <div className="conv-error">
        <span>{state.conversationsError || "Не удалось загрузить чаты"}</span>
        <button type="button" className="conv-retry" onClick={() => void retryConversations()}>
          Повторить
        </button>
      </div>
    );
  }
  if (state.conversations.length === 0) {
    return <div className="conv-empty">Пока нет задач</div>;
  }

  const groups = groupConversationsByTime(state.conversations, new Date());

  return (
    <div className="conv-list">
      {groups.map((group) => (
        <div className="conv-group" key={group.label}>
          <div className="conv-group-label">{group.label}</div>
          {group.items.map((c) => (
            <ConversationItem
              key={c.id}
              conv={c}
              active={c.id === state.currentId && state.view === "chat"}
              onOpen={() => void openConversation(c.id)}
              onDelete={() => void removeConversation(c.id)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
