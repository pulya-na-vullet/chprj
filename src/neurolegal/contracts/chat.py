"""Public DTOs for the agent HTTP surface.

The SSE wire contract is documented here: `event` is the SSE event name; the
matching `*EventData` model is the JSON shape of the `data:` field."""

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    # review.py imports Citation from this module, so chat.py must not import
    # review.py at runtime (cycle). See contracts/review.py's module
    # docstring and contracts/__init__.py's MessageOut.model_rebuild() call.
    from neurolegal.contracts.review import ReviewReportData


class ReviewCommand(BaseModel):
    type: Literal["risk_review"]
    document_id: str
    playbook_id: str
    role: str | None = Field(None, max_length=100)


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    acts: list[str] | None = None
    command: ReviewCommand | None = None
    # E20: вход из витрины «Шаблоны» — фронт стартует новую беседу,
    # передавая slug шаблона; поля шаблона попадают в системный контекст.
    template_slug: str | None = None


class Citation(BaseModel):
    act_short_name: str
    kind: str
    number: str
    title: str | None = None
    full_text: str
    score: float


class WebSource(BaseModel):
    url: str
    title: str
    snippet: str | None = None


class FoundArticle(BaseModel):
    act: str
    number: str


class SessionEventData(BaseModel):
    session_id: str


class ToolCallEventData(BaseModel):
    tool: str
    args: dict[str, object]
    error: bool = False


class ToolResultEventData(BaseModel):
    found: list[FoundArticle]


class ReasoningEventData(BaseModel):
    text: str


class DeltaEventData(BaseModel):
    text: str


class ResetDeltaEventData(BaseModel):
    """Empty payload — the event name carries all the meaning.

    Signals the frontend to discard any draft `delta` text accumulated this
    turn. The backend emits this when the LLM streamed visible text and then
    asked for a tool call; the text was not the final answer."""


class CitationsEventData(BaseModel):
    articles: list[Citation]


class WebSourcesEventData(BaseModel):
    sources: list[WebSource]


class DoneEventData(BaseModel):
    message_id: str | None
    stopped: bool = False


class ErrorEventData(BaseModel):
    detail: str


class AskEventData(BaseModel):
    """Data shape of the `ask` SSE event — the agent pauses a turn to ask the
    user a clarifying question (e.g. which side of the contract they are)."""

    question: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True
    # T-0051: различает review-вопрос роли и универсальный LLM-вопрос —
    # фронту нужен kind вживую (FINISH_TURN складывает ask в сообщение).
    kind: Literal["review_role", "ask_user"] = "review_role"
    # E20: вопрос задан в шаблонном режиме — только такой ask разрешает
    # фронту перехватывать кнопки «Выбрать из „Файлов“» / «Загрузить
    # документ» (пикер/выбор файла); вне шаблонного хода похожие кнопки
    # остаются обычными ответами.
    template: bool = False


class MessageAsk(BaseModel):
    """Persisted shape of a paused-for-input turn, stored on the message and
    replayed via `GET /conversations/{id}/messages` (`MessageOut.ask`)."""

    kind: Literal["review_role", "review_failed", "ask_user"]
    question: str | None = None
    options: list[str] = Field(default_factory=list)
    document_id: str | None = None
    playbook_id: str | None = None
    role: str | None = None
    error: str | None = None
    # E20: см. AskEventData.template — признак шаблонного вопроса; хранится
    # на сообщении и переживает перезагрузку истории.
    template: bool = False


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: str
    # T-0014: итог последнего ответа ассистента для «Реестра задач»;
    # None — в беседе ещё нет ответа
    preview: str | None = None


class ConversationsResponse(BaseModel):
    conversations: list[ConversationOut]


TemplateValueSource = Literal["profile", "document", "user"]


class TemplateDraftFieldOut(BaseModel):
    name: str
    label: str
    value: str
    source: TemplateValueSource


class TemplateDraftRef(BaseModel):
    slug: str
    title: str


class TemplateDraftEventData(BaseModel):
    """Data shape of the `template_draft` SSE event (E20): панель сводки
    staged-черновика. Тот же payload хранится на сообщении
    (`MessageOut.template_draft`) — панель переживает перезагрузку истории."""

    template: TemplateDraftRef
    fields: list[TemplateDraftFieldOut]


class DocumentReadyEventData(BaseModel):
    """Data shape of the `document_ready` SSE event (E20): готовый .docx
    сохранён в библиотеку «Файлы» и привязан к беседе. Тот же payload — на
    сообщении (`MessageOut.template_doc`)."""

    document_id: str
    filename: str
    fields_filled: int


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] | None
    web_sources: list[WebSource] | None = None
    review: "ReviewReportData | None" = None
    created_at: str
    stopped: bool = False
    ask: MessageAsk | None = None
    template_draft: TemplateDraftEventData | None = None
    template_doc: DocumentReadyEventData | None = None


class MessagesResponse(BaseModel):
    messages: list[MessageOut]
