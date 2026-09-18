"""SSE event types emitted by the ChatAgent.

Each event carries an `event` name (the SSE event field) and a `data` dict
(serialised to JSON for the SSE data field).

The `.data` shape is defined by the matching `*EventData` Pydantic model in
``neurolegal.contracts.chat`` — the dataclass holds the constructor args, the
contracts model owns the wire format. If either side renames or retypes a
field, the type checker catches it.
"""

from dataclasses import dataclass
from typing import ClassVar, Literal

from neurolegal.contracts import (
    AskEventData,
    CitationsEventData,
    CoverageStatus,
    DeltaEventData,
    DocumentReadyEventData,
    DoneEventData,
    ErrorEventData,
    FoundArticle,
    ReasoningEventData,
    ResetDeltaEventData,
    ReviewProgressEventData,
    ReviewReportData,
    SessionEventData,
    TemplateDraftEventData,
    TemplateDraftFieldOut,
    TemplateDraftRef,
    ToolCallEventData,
    ToolResultEventData,
    WebSourcesEventData,
)


@dataclass
class SessionEvent:
    event: ClassVar[str] = "session"
    session_id: str

    @property
    def data(self) -> dict[str, object]:
        return SessionEventData(session_id=self.session_id).model_dump()


@dataclass
class ToolCallEvent:
    event: ClassVar[str] = "tool_call"
    tool: str
    args: dict[str, object]
    error: bool = False

    @property
    def data(self) -> dict[str, object]:
        return ToolCallEventData(tool=self.tool, args=self.args, error=self.error).model_dump()


@dataclass
class ReasoningEvent:
    event: ClassVar[str] = "reasoning"
    text: str

    @property
    def data(self) -> dict[str, object]:
        return ReasoningEventData(text=self.text).model_dump()


@dataclass
class ToolResultEvent:
    event: ClassVar[str] = "tool_result"
    found: list[dict[str, object]]

    @property
    def data(self) -> dict[str, object]:
        # The Pydantic model coerces each dict into a FoundArticle, validating
        # the {"act", "number"} shape at construction time.
        articles = [FoundArticle.model_validate(item) for item in self.found]
        return ToolResultEventData(found=articles).model_dump()


@dataclass
class DeltaEvent:
    event: ClassVar[str] = "delta"
    text: str

    @property
    def data(self) -> dict[str, object]:
        return DeltaEventData(text=self.text).model_dump()


@dataclass
class ResetDeltaEvent:
    """Frontend must discard any draft `delta` text accumulated this turn.

    Emitted when the model streamed visible text and then asked for a tool;
    the text was not the final answer."""

    event: ClassVar[str] = "reset_delta"

    @property
    def data(self) -> dict[str, object]:
        return ResetDeltaEventData().model_dump()


@dataclass
class CitationsEvent:
    event: ClassVar[str] = "citations"
    articles: list[dict[str, object]]

    @property
    def data(self) -> dict[str, object]:
        # Validates each dict against the Citation shape on emission — drift
        # caught at the wire edge.
        return CitationsEventData.model_validate({"articles": self.articles}).model_dump()


@dataclass
class WebSourcesEvent:
    event: ClassVar[str] = "web_sources"
    sources: list[dict[str, object]]

    @property
    def data(self) -> dict[str, object]:
        return WebSourcesEventData.model_validate({"sources": self.sources}).model_dump()


@dataclass
class ReviewProgressEvent:
    event: ClassVar[str] = "review_progress"
    rule_id: str
    title: str
    index: int
    total: int
    status: CoverageStatus | Literal["running"]

    @property
    def data(self) -> dict[str, object]:
        return ReviewProgressEventData(
            rule_id=self.rule_id,
            title=self.title,
            index=self.index,
            total=self.total,
            status=self.status,
        ).model_dump()


@dataclass
class ReviewReportEvent:
    event: ClassVar[str] = "review_report"
    report: ReviewReportData

    @property
    def data(self) -> dict[str, object]:
        return self.report.model_dump()


@dataclass
class AskEvent:
    """Agent pauses the turn to ask the user a clarifying question.

    T-0046: a `risk_review` command without a pinned party role emits this
    instead of running the pipeline — `options` are the playbook's declared
    roles. T-0051: the LLM's ask_user tool emits the same event with
    kind="ask_user". The user's next plain message is treated as the answer
    (review_role — via ChatAgent.run's pending-ask interception; ask_user —
    simply as the next turn the model sees in history)."""

    event: ClassVar[str] = "ask"
    question: str
    options: list[str]
    allow_free_text: bool = True
    kind: Literal["review_role", "ask_user"] = "review_role"
    # E20: вопрос задан в шаблонном режиме — фронт может перехватывать кнопки
    # пикера/загрузки только для таких ask'ов.
    template: bool = False

    @property
    def data(self) -> dict[str, object]:
        return AskEventData(
            question=self.question,
            options=self.options,
            allow_free_text=self.allow_free_text,
            kind=self.kind,
            template=self.template,
        ).model_dump()


@dataclass
class TemplateDraftEvent:
    """Панель сводки staged-черновика (E20): что пользователь видит здесь,
    то ровно и уйдёт в рендер после подтверждения."""

    event: ClassVar[str] = "template_draft"
    slug: str
    title: str
    fields: list[TemplateDraftFieldOut]

    @property
    def data(self) -> dict[str, object]:
        return TemplateDraftEventData(
            template=TemplateDraftRef(slug=self.slug, title=self.title),
            fields=self.fields,
        ).model_dump()


@dataclass
class DocumentReadyEvent:
    """Готовый .docx сохранён в библиотеку «Файлы» и привязан к беседе (E20)."""

    event: ClassVar[str] = "document_ready"
    document_id: str
    filename: str
    fields_filled: int

    @property
    def data(self) -> dict[str, object]:
        return DocumentReadyEventData(
            document_id=self.document_id,
            filename=self.filename,
            fields_filled=self.fields_filled,
        ).model_dump()


@dataclass
class DoneEvent:
    event: ClassVar[str] = "done"
    message_id: str | None
    stopped: bool = False

    @property
    def data(self) -> dict[str, object]:
        return DoneEventData(message_id=self.message_id, stopped=self.stopped).model_dump()


@dataclass
class ErrorEvent:
    event: ClassVar[str] = "error"
    detail: str

    @property
    def data(self) -> dict[str, object]:
        return ErrorEventData(detail=self.detail).model_dump()


AgentEvent = (
    SessionEvent
    | ToolCallEvent
    | ToolResultEvent
    | ReasoningEvent
    | DeltaEvent
    | ResetDeltaEvent
    | CitationsEvent
    | WebSourcesEvent
    | ReviewProgressEvent
    | ReviewReportEvent
    | TemplateDraftEvent
    | DocumentReadyEvent
    | AskEvent
    | DoneEvent
    | ErrorEvent
)
