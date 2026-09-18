"""Базовые типы для тулзов агента: контекст вызова, единый результат, протокол."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.tools.documents_client import DocumentsClient
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.agent.tools.templates_client import AgentTemplatesClient
from neurolegal.contracts import SearchedArticle, ToolsSettings, WebSource

if TYPE_CHECKING:
    from neurolegal.agent.chat.events import AgentEvent


@dataclass
class ToolContext:
    rag_client: RagClient
    acts: list[str] | None
    tools: ToolsSettings
    tavily_api_key: str | None = None
    # Documents the hub reports as `ready` for this conversation. read_document
    # validates the id is in this set, then fetches content from the hub.
    document_ids: frozenset[str] = field(default_factory=frozenset)
    documents_client: DocumentsClient | None = None
    # The requesting user's id, forwarded to documents_client calls (X-User-Id)
    # so hub-side document reads are attributable. Empty string when no user
    # context applies (tool tests that never touch documents_client).
    user_id: str = ""
    # E20: тулзы шаблонов. conversation_id владельчески проверен агентом
    # (ensure_conversation) до вызова любого тулза; store — тот же
    # per-request ConversationStore, каким пользуется агент (черновики коммитятся
    # в момент stage, не дожидаясь конца хода).
    templates_client: AgentTemplatesClient | None = None
    conversation_store: ConversationStore | None = None
    conversation_id: str = ""


@dataclass
class ToolOutcome:
    tool_result: str
    articles: list[SearchedArticle] = field(default_factory=list)
    web_sources: list[WebSource] = field(default_factory=list)
    unavailable: bool = False
    # События, которые агент должен отдать в SSE-поток сразу после тулза
    # (E20: template_draft / document_ready).
    events: list["AgentEvent"] = field(default_factory=list)


class ToolHandler(Protocol):
    async def __call__(self, arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome: ...
