"""The ChatAgent: a tool-calling, multi-turn loop over an LLM and a tool registry.

Per turn: classify intent, load history, persist the user message, run the
LLM↔tool loop up to `behavior.max_tool_iterations` times (default 8, see
`contracts/agent_settings.py`), stream the answer, then persist the
assistant message with citations and web_sources. On hitting the cap the
turn answers with the fixed CAP_NOTE — streamed AND stored.

Intent determines both the system prompt and tool exposure: LEGAL turns get
the registered research tools, while text/smalltalk turns run without tools.
Citations and web_sources are emitted whenever tool data is present.

One exception: the LEGAL safety floor. If intent is LEGAL and no articles
were found (after the full tool loop), the agent overrides the draft answer
with NO_BASIS_NOTE or SEARCH_UNAVAILABLE_NOTE so the model cannot hallucinate
legal claims without a corpus basis.

Reset-delta contract: if the model streams visible text and then asks for a
tool, that text was not the final answer. The agent emits a `reset_delta`
event so the frontend drops what it showed; only post-reset text becomes the
stored answer.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal, cast

from neurolegal.agent.chat.answers import CAP_NOTE, NO_BASIS_NOTE, SEARCH_UNAVAILABLE_NOTE
from neurolegal.agent.chat.events import (
    AgentEvent,
    AskEvent,
    CitationsEvent,
    DeltaEvent,
    DocumentReadyEvent,
    DoneEvent,
    ErrorEvent,
    ReasoningEvent,
    ResetDeltaEvent,
    ReviewReportEvent,
    TemplateDraftEvent,
    ToolCallEvent,
    ToolResultEvent,
    WebSourcesEvent,
)
from neurolegal.agent.chat.intent import Intent
from neurolegal.agent.chat.intent import classify_intent as default_classify_intent
from neurolegal.agent.chat.prompts import (
    ASK_USER_NOTE,
    SYSTEM_PROMPT,
    TEMPLATE_PROMPT,
    TEXT_TASK_PROMPT,
)
from neurolegal.agent.chat.tools.ask_user import ASK_USER_TOOL, parse_ask_user_args
from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.chat.tools.read_document import READ_DOCUMENT_TOOL
from neurolegal.agent.chat.tools.read_document import handle as handle_read_document
from neurolegal.agent.chat.tools.registry import build_registry
from neurolegal.agent.chat.tools.templates import (
    LIST_TEMPLATES_TOOL,
    RENDER_TEMPLATE_TOOL,
    STAGE_TEMPLATE_TOOL,
    handle_list_templates,
    handle_render_template,
    handle_stage_template,
)
from neurolegal.agent.llm.client import ChatLLM
from neurolegal.agent.llm.types import (
    ChatMessage,
    ReasoningChunk,
    TextChunk,
    ToolCallRequest,
    ToolSpec,
)
from neurolegal.agent.review.engine import ReviewEngine
from neurolegal.agent.review.playbook import Playbook
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.tools.documents_client import DocumentsClient, DocumentsClientError
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.agent.tools.templates_client import (
    AgentTemplatesClient,
    TemplatesClientError,
    TemplatesNotFoundError,
)
from neurolegal.contracts import (
    BehaviorSettings,
    Citation,
    MessageAsk,
    ReviewCommand,
    ReviewReportData,
    SearchedArticle,
    ToolsSettings,
    WebSource,
)

logger = logging.getLogger(__name__)

# T-0046: the question asked when a risk_review command arrives without a
# pinned party role. Persisted as the assistant message content and as
# MessageAsk.question (both must match — the frontend shows one, the SSE
# AskEvent carries the other).
_REVIEW_ROLE_QUESTION = "Кто вы по этому договору? От этого зависит, чьи риски я буду искать."


class ConversationNotFound(Exception):  # noqa: N818
    def __init__(self, session_id: str) -> None:
        super().__init__(f"conversation not found: {session_id}")
        self.session_id = session_id


def _citation(a: SearchedArticle) -> dict[str, object]:
    return Citation(
        act_short_name=a.act_short_name,
        kind=a.act_kind,
        number=a.number,
        title=a.title,
        full_text=a.full_text,
        score=a.score,
    ).model_dump()


def _tool_result_has_error(tool_result: str) -> bool:
    """True when a tool's JSON result carries an ``error`` key.

    ``tool_result`` is the raw string a tool returned; read_document emits
    ``{"error": ...}`` on a missing document/section. Non-JSON or non-object
    payloads are treated as error-free (they are not a read_document failure).
    """
    try:
        parsed = json.loads(tool_result)
    except (ValueError, TypeError):
        return False
    return isinstance(parsed, dict) and "error" in parsed


async def _iter_until_stop[T](
    source: AsyncIterator[T], stop: asyncio.Event | None
) -> AsyncIterator[T]:
    """Yield from `source` until it ends or `stop` is set.

    On stop the pending anext is cancelled and the source generator is
    closed — for the LLM stream that tears down the underlying HTTP stream,
    so generation actually halts upstream.
    """
    if stop is None:
        async for item in source:
            yield item
        return
    stop_task = asyncio.ensure_future(stop.wait())
    next_task: asyncio.Task[T] | None = None
    try:
        while True:
            next_task = asyncio.ensure_future(anext(source))
            await asyncio.wait(
                cast(set["asyncio.Future[object]"], {next_task, stop_task}),
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Stop первым: если стоп и чанк завершились в одном тике, чанк
            # отбрасывается — пользователь уже остановил ход.
            if stop_task.done():
                return
            try:
                item = next_task.result()
            except StopAsyncIteration:
                return
            yield item
    finally:
        # Обрыв клиента (cancel scope) может прилететь, пока next_task ещё
        # ВНУТРИ генератора source. Сначала гасим задачи и дожидаемся их,
        # и только затем aclose() — иначе «aclose(): asynchronous generator
        # is already running» (наблюдалось вживую на disconnect во время
        # LLM-вызова).
        for task in (next_task, stop_task):
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await task
        aclose = getattr(source, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await aclose()


async def _call_tool_or_stop(
    call: Awaitable[ToolOutcome], stop: asyncio.Event | None
) -> ToolOutcome | None:
    """Await the tool call, or return None if `stop` fires first (tool task
    is cancelled — this is our own cooperative cancellation, not anyio's)."""
    if stop is None:
        return await call
    tool_task = asyncio.ensure_future(call)
    stop_task = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait(
            cast(set["asyncio.Future[object]"], {tool_task, stop_task}),
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Stop первым (симметрично _iter_until_stop): завершившийся в тот же
        # тик tool-результат отбрасывается.
        if stop_task.done():
            tool_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tool_task
            return None
        return tool_task.result()
    finally:
        stop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stop_task


_RISK_LEVEL_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
_RISK_EXPLANATION_PREVIEW_CHARS = 200


def _review_summary(report: ReviewReportData) -> str:
    """Markdown summary persisted as the assistant message for a risk_review turn."""
    counts = {"high": 0, "medium": 0, "low": 0}
    for risk in report.risks:
        counts[risk.level] += 1
    missing = sum(1 for c in report.coverage if c.status == "missing")
    top = sorted(report.risks, key=lambda r: _RISK_LEVEL_ORDER[r.level])[:3]
    lines = [
        f"# Проверка по плейбуку {report.playbook_name}",
        f"Риски: high {counts['high']}, medium {counts['medium']}, low {counts['low']}",
        *(
            f"— [{risk.level}] {risk.title}: {risk.explanation[:_RISK_EXPLANATION_PREVIEW_CHARS]}"
            for risk in top
        ),
        f"Покрытие: {len(report.coverage)} правил; рисков {len(report.risks)}; "
        f"отсутствуют клаузы {missing}",
    ]
    return "\n".join(lines)


class ChatAgent:
    def __init__(
        self,
        llm: ChatLLM,
        rag_client: RagClient,
        store: ConversationStore,
        max_tool_iterations: int | None = None,
        classify_intent: Callable[[str], Intent] = default_classify_intent,
        behavior: BehaviorSettings | None = None,
        tools: ToolsSettings | None = None,
        tavily_api_key: str | None = None,
        documents_client: DocumentsClient | None = None,
        playbooks: dict[str, Playbook] | None = None,
        review_llm: ChatLLM | None = None,
        review_concurrency: int = 4,
        templates_client: AgentTemplatesClient | None = None,
    ) -> None:
        self._llm = llm
        self._rag = rag_client
        self._store = store
        self._behavior = behavior or BehaviorSettings()
        self._tools = tools or ToolsSettings()
        self._tavily_api_key = tavily_api_key
        self._documents_client = documents_client
        self._templates_client = templates_client
        self._playbooks = playbooks or {}
        self._review_llm = review_llm
        self._review_concurrency = review_concurrency
        self._registry = build_registry(self._tools)
        self._max_iters = (
            max_tool_iterations
            if max_tool_iterations is not None
            else self._behavior.max_tool_iterations
        )
        self._classify_intent = classify_intent

    async def ensure_conversation(self, session_id: str | None, user_id: str) -> tuple[str, bool]:
        """Return (conversation_id, is_new). Raises ConversationNotFound for an
        unknown non-null session_id, or one that belongs to another user (never
        distinguish "not yours" from "doesn't exist" outward)."""
        if session_id is None:
            conv_id = await self._store.create_conversation(user_id)
            await self._store.commit()
            return conv_id, True
        if not await self._store.conversation_exists(session_id, user_id):
            raise ConversationNotFound(session_id)
        return session_id, False

    async def run(
        self,
        conversation_id: str,
        user_message: str,
        acts: list[str] | None = None,
        *,
        user_id: str,
        profile_note: str | None = None,
        stop: asyncio.Event | None = None,
        template_slug: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        # T-0046: a pending "which role are you" question from a risk_review
        # turn intercepts the next plain message — it is the answer, not a
        # new free-form turn. Delegate wholesale to run_review: it persists
        # the user message itself, so this branch must not persist it again.
        last = await self._store.last_message(conversation_id, user_id)
        if last is not None and last.role == "assistant" and last.ask is not None:
            pending = MessageAsk.model_validate(last.ask)
            if (
                pending.kind == "review_role"
                and pending.document_id is not None
                and pending.playbook_id is not None
            ):
                pending_role = user_message.strip()
                # A whitespace-only reply is not an answer to the role
                # question — fall through to the normal run() path below as
                # if there were no pending ask, rather than starting a review
                # with an empty role.
                if pending_role:
                    command = ReviewCommand(
                        type="risk_review",
                        document_id=pending.document_id,
                        playbook_id=pending.playbook_id,
                        role=pending_role[:100],
                    )
                    async for review_event in self.run_review(
                        conversation_id, command, user_message, user_id=user_id, stop=stop
                    ):
                        yield review_event
                    return

        # E20: шаблонный режим. Явный template_slug (вход из витрины) или
        # активный (не отрендеренный) черновик беседы включают TEMPLATE-интент
        # без классификатора: пользователь уже в диалоге заполнения.
        draft = await self._store.get_template_draft(conversation_id)
        if template_slug or (draft is not None and draft.rendered_at is None):
            intent = Intent.TEMPLATE
        else:
            intent = self._classify_intent(user_message)

        template_note: str | None = None
        if intent == Intent.TEMPLATE:
            template_note = await self._prepare_template_turn(
                conversation_id, template_slug or (draft.template_slug if draft else None)
            )

        history = await self._store.load_history(conversation_id, user_id)
        await self._store.append_message(conversation_id, user_id, "user", user_message)
        await self._store.commit()

        if intent == Intent.TEMPLATE:
            system_prompt = TEMPLATE_PROMPT
            if template_note:
                system_prompt = f"{system_prompt}\n\n{template_note}"
        elif intent == Intent.LEGAL:
            system_prompt = self._behavior.system_prompt_legal or SYSTEM_PROMPT
        else:
            system_prompt = self._behavior.system_prompt_text or TEXT_TASK_PROMPT

        # T-0128: профильный блок пользователя (готовая строка из
        # build_profile_note, собирает роут по UserRow). Дописывается после
        # базового промпта — правила ответов и цитирования нетронуты.
        if profile_note:
            system_prompt = f"{system_prompt}\n\n{profile_note}"

        # Legal turns get the research tools. Text tasks and smalltalk should
        # not be able to emit legal citations by accidentally calling RAG.
        # Copy (never mutate self._registry) since read_document may be added
        # below for this turn only. Template turns get only the template tools
        # (+ask_user/read_document) — rag_search и цитаты в этом режиме не
        # участвуют (спека E20 §6).
        if intent == Intent.LEGAL:
            active_registry = dict(self._registry)
        elif intent == Intent.TEMPLATE:
            active_registry = {
                LIST_TEMPLATES_TOOL.name: (LIST_TEMPLATES_TOOL, handle_list_templates),
                STAGE_TEMPLATE_TOOL.name: (STAGE_TEMPLATE_TOOL, handle_stage_template),
                RENDER_TEMPLATE_TOOL.name: (RENDER_TEMPLATE_TOOL, handle_render_template),
            }
        else:
            active_registry = {}

        docs = []
        if self._documents_client:
            try:
                docs = await self._documents_client.list_for_conversation(conversation_id, user_id)
            except DocumentsClientError:
                docs = []  # hub down → no documents this turn; never crash the turn
        ready_docs = [d for d in docs if d.status == "ready"]
        if ready_docs:
            doc_lines = "\n".join(f"- {d.filename} (id={d.id})" for d in ready_docs)
            system_prompt = f"{system_prompt}\n\nВ беседе загружены документы:\n{doc_lines}"
            # read_document is exposed for every intent (LEGAL and TEXT_TASK
            # alike): a user may ask to summarize/rephrase an uploaded document
            # without it being a legal question.
            active_registry["read_document"] = (READ_DOCUMENT_TOOL, handle_read_document)

        # T-0051: универсальная уточняющая тулза. Smalltalk её не получает —
        # приветствию уточнения не нужны; review-путь (run_review) реестром
        # не пользуется вовсе. Терминальна: перехватывается в цикле ниже, в
        # registry не входит.
        ask_user_enabled = intent != Intent.SMALLTALK
        tools_specs: list[ToolSpec] = [spec for spec, _ in active_registry.values()]
        if ask_user_enabled:
            tools_specs.append(ASK_USER_TOOL)
            system_prompt = f"{system_prompt}\n\n{ASK_USER_NOTE}"

        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
        window = self._behavior.history_window
        if window is None:
            recent = history
        elif window == 0:
            recent = []
        else:
            recent = history[-window:]
        for m in recent:
            # stored roles are only "user"/"assistant"
            role: Literal["user", "assistant"] = "assistant" if m.role == "assistant" else "user"
            messages.append(ChatMessage(role=role, content=m.content))
        messages.append(ChatMessage(role="user", content=user_message))

        articles_seen: dict[str, SearchedArticle] = {}
        web_sources_seen: dict[str, WebSource] = {}
        answer_parts: list[str] = []
        capped = True
        search_unavailable = False
        # A successful read_document call is a valid basis for a LEGAL answer
        # even though it never populates articles_seen — the safety floor below
        # must not overwrite an answer grounded in the uploaded document.
        document_read = False

        ctx = ToolContext(
            rag_client=self._rag,
            acts=acts,
            tools=self._tools,
            tavily_api_key=self._tavily_api_key,
            document_ids=frozenset(d.id for d in ready_docs),
            documents_client=self._documents_client,
            user_id=user_id,
            templates_client=self._templates_client,
            conversation_store=self._store,
            conversation_id=conversation_id,
        )
        # E20: payload'ы карточек шаблонного флоу этого хода — прикрепляются
        # к сохранённому ответу, чтобы пережить перезагрузку истории.
        template_draft_payload: dict[str, object] | None = None
        template_doc_payload: dict[str, object] | None = None

        stopped = False
        for _ in range(self._max_iters):
            if stop is not None and stop.is_set():
                # Стоп между итерациями (напр. сработал на последнем tool):
                # не начинать новый LLM-запрос.
                stopped = True
                capped = False
                break
            tool_calls: list[ToolCallRequest] = []
            text_streamed_this_turn = False
            async for event in _iter_until_stop(self._llm.stream(messages, tools_specs), stop):
                if isinstance(event, TextChunk):
                    answer_parts.append(event.text)
                    text_streamed_this_turn = True
                    yield DeltaEvent(text=event.text)
                elif isinstance(event, ReasoningChunk):
                    # Thinking trace: shown live, never part of the stored answer.
                    yield ReasoningEvent(text=event.text)
                else:
                    tool_calls.append(event)

            if stop is not None and stop.is_set():
                stopped = True
                capped = False
                break

            if not tool_calls:
                capped = False
                break

            # Discard any partial text the user already saw: it wasn't the
            # final answer. Tell the frontend to drop its draft.
            if text_streamed_this_turn:
                answer_parts.clear()
                yield ResetDeltaEvent()
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ],
                )
            )
            for tc in tool_calls:
                if ask_user_enabled and tc.name == "ask_user":
                    parsed = parse_ask_user_args(tc.arguments)
                    if parsed is not None:
                        question, options = parsed
                        # E20: только шаблонный ход помечает ask как template —
                        # фронт перехватывает кнопки пикера/загрузки строго по
                        # этому признаку, не по тексту кнопок.
                        is_template_ask = intent == Intent.TEMPLATE
                        ask = MessageAsk(
                            kind="ask_user",
                            question=question,
                            options=options,
                            template=is_template_ask,
                        )
                        # ask_user терминален: карточки, показанные в этом же
                        # ходе (сводка черновика — основной путь E20, её сам
                        # stage_template велит подтверждать через ask_user),
                        # уезжают на это сообщение, иначе после перезагрузки
                        # истории остался бы вопрос без предмета подтверждения.
                        message_id = await self._store.append_message(
                            conversation_id,
                            user_id,
                            "assistant",
                            question,
                            ask=ask.model_dump(),
                            template_draft=template_draft_payload,
                            template_doc=template_doc_payload,
                        )
                        await self._store.commit()
                        yield AskEvent(
                            question=question,
                            options=options,
                            kind="ask_user",
                            template=is_template_ask,
                        )
                        yield DoneEvent(message_id=message_id, stopped=False)
                        return
                    # Невалидный вызов: ошибочный результат (error) — модель
                    # попробует снова, в рамках лимита итераций.
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=tc.id,
                            name=tc.name,
                            content=json.dumps(
                                {"error": "ask_user требует непустой question"},
                                ensure_ascii=False,
                            ),
                        )
                    )
                    continue
                yield ToolCallEvent(tool=tc.name, args=tc.arguments)
                entry = active_registry.get(tc.name)
                if entry is None:
                    outcome: ToolOutcome | None = ToolOutcome(
                        json.dumps({"error": "unknown tool"}, ensure_ascii=False)
                    )
                else:
                    outcome = await _call_tool_or_stop(entry[1](tc.arguments, ctx), stop)
                if outcome is None:
                    stopped = True
                    break
                search_unavailable = search_unavailable or outcome.unavailable
                found: list[dict[str, object]] = cast(
                    list[dict[str, object]],
                    [{"act": a.act_short_name, "number": a.number} for a in outcome.articles][:6],
                )
                yield ToolResultEvent(found=found)
                for extra in outcome.events:
                    if isinstance(extra, TemplateDraftEvent):
                        template_draft_payload = extra.data
                    elif isinstance(extra, DocumentReadyEvent):
                        template_doc_payload = extra.data
                    yield extra
                if tc.name == "read_document" and not _tool_result_has_error(outcome.tool_result):
                    document_read = True
                for a in outcome.articles:
                    articles_seen[str(a.article_id)] = a
                for w in outcome.web_sources:
                    web_sources_seen[w.url] = w
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=tc.id,
                        name=tc.name,
                        content=outcome.tool_result,
                    )
                )
            if stopped:
                capped = False
                break

        # When every basis-gathering path failed because RAG itself was down,
        # saying "no relevant norms exist" would be a false legal statement —
        # report the outage instead, on both the capped and no-basis paths.
        outage = search_unavailable and not articles_seen
        if stopped:
            pass  # частичный ответ остаётся как есть — честнее, чем подмена нотой
        elif capped:
            logger.warning("chat_agent_iteration_cap", extra={"conversation_id": conversation_id})
            note = SEARCH_UNAVAILABLE_NOTE if outage else CAP_NOTE
            answer_parts = [note]
            yield DeltaEvent(text=note)
        elif intent == Intent.LEGAL and not articles_seen and not document_read:
            # Safety floor for LEGAL turns: no RAG basis = no answer, even if
            # the model streamed text directly. Clear the draft on the
            # frontend so the hallucinated answer doesn't linger.
            if answer_parts:
                yield ResetDeltaEvent()
            note = SEARCH_UNAVAILABLE_NOTE if outage else NO_BASIS_NOTE
            answer_parts = [note]
            yield DeltaEvent(text=note)

        answer = "".join(answer_parts)
        citations = [_citation(a) for a in articles_seen.values()]
        web_sources = list(web_sources_seen.values())
        yield CitationsEvent(articles=citations)
        if web_sources:
            yield WebSourcesEvent(sources=[w.model_dump() for w in web_sources])
        if stopped and not answer:
            # Стоп до первого текста: в беседе остаётся только вопрос.
            yield DoneEvent(message_id=None, stopped=True)
            return
        message_id = await self._store.append_message(
            conversation_id,
            user_id,
            "assistant",
            answer,
            citations=citations or None,
            web_sources=[w.model_dump() for w in web_sources] or None,
            stopped=stopped,
            template_draft=template_draft_payload,
            template_doc=template_doc_payload,
        )
        await self._store.commit()
        yield DoneEvent(message_id=message_id, stopped=stopped)

    async def _prepare_template_turn(self, conversation_id: str, slug: str | None) -> str | None:
        """Контекст шаблонного хода: привязка беседы к шаблону (вход из
        витрины) плюс блок системного промпта: поля шаблона и уже собранные
        значения. Недоступность сервиса либо снятый шаблон превращаются в
        честную ноту — ход не ломается."""
        if self._templates_client is None:
            return "Сервис шаблонов сейчас недоступен — честно сообщи об этом."
        if slug is None:
            return None  # шаблон ещё не выбран — модель начнёт через list_templates
        try:
            detail = await self._templates_client.get_template(slug)
        except TemplatesNotFoundError:
            return (
                f"Шаблон «{slug}» больше недоступен (снят с публикации) — "
                "сообщи пользователю и предложи выбрать другой через list_templates."
            )
        except TemplatesClientError:
            return "Сервис шаблонов сейчас недоступен — честно сообщи об этом."
        await self._store.bind_template(conversation_id, detail.slug, detail.title)
        await self._store.commit()
        lines = [f"Выбран шаблон: «{detail.title}» (slug: {detail.slug})."]
        lines.append("Поля шаблона:")
        for f in detail.fields:
            req = "обязательное" if f.required else "необязательное"
            hint = f"; подсказка: {f.hint}" if f.hint else ""
            lines.append(f"- {f.name} — {f.label} ({f.kind}, {req}{hint})")
        draft = await self._store.get_template_draft(conversation_id)
        if draft is not None and draft.template_slug == detail.slug and draft.values:
            staged = ", ".join(f"{k}={v}" for k, v in draft.values.items())
            lines.append(f"Уже собрано (staged): {staged}")
        return "\n".join(lines)

    async def run_review(
        self,
        conversation_id: str,
        command: ReviewCommand,
        user_message: str,
        *,
        user_id: str,
        stop: asyncio.Event | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run a `risk_review` slash command as its own SSE turn.

        Validates the document/playbook up front. On an early failure
        (unknown playbook, document not found/not ready, hub outage) it
        persists both the user message and a `review_failed`-tagged
        assistant message, so the conversation history stays whole, then
        emits `ErrorEvent` + `DoneEvent`.

        The role question is asked only for playbooks that declare party
        roles (`playbook.roles` non-empty, e.g. contracts: Заказчик/
        Исполнитель): when `command.role` is unset, the turn pauses instead
        of running the pipeline, persists the user message, then a
        `review_role`-tagged assistant question (the playbook's declared
        roles as options) and emits `AskEvent` + `DoneEvent`. Document
        validation (found in this conversation, status ready) still runs
        first, but the role check happens before `get_content` — an ask
        turn never fetches section content it is about to discard.
        `ChatAgent.run` intercepts the user's next plain message as the
        answer and re-enters here with the role filled in (see its T-0046
        comment). Roleless playbooks (service documents) run without a
        role — `role=None` reaches `engine.run` unchanged, and the engine
        + `_with_role_prefix` already treat `None`/empty as "no role
        prefix".

        With a role in hand it persists the user message, streams
        `ReviewEngine.run`'s progress and report events, then persists an
        assistant message carrying both a markdown summary and the full
        `ReviewReportData`. A `ReviewEngineError` mid-run persists a
        `review_failed`-tagged assistant message instead (only a partial
        report was produced). A stop before the report is produced is not a
        failure — nothing new is persisted, same as before T-0046.
        """
        if self._documents_client is None or not self._playbooks:
            yield ErrorEvent(detail="Проверка по плейбуку недоступна в этой конфигурации")
            return
        playbook = self._playbooks.get(command.playbook_id)
        if playbook is None:
            detail = f"Неизвестный плейбук: {command.playbook_id}"
            await self._store.append_message(conversation_id, user_id, "user", user_message)
            message_id = await self._persist_review_failure(
                conversation_id, user_id, command, detail
            )
            yield ErrorEvent(detail=detail)
            yield DoneEvent(message_id=message_id)
            return
        try:
            docs = await self._documents_client.list_for_conversation(conversation_id, user_id)
            match = next((d for d in docs if d.id == command.document_id), None)
            if match is None:
                detail = "Документ не найден в этой беседе"
                await self._store.append_message(conversation_id, user_id, "user", user_message)
                message_id = await self._persist_review_failure(
                    conversation_id, user_id, command, detail
                )
                yield ErrorEvent(detail=detail)
                yield DoneEvent(message_id=message_id)
                return
            if match.status != "ready":
                detail = f"Документ ещё не готов к проверке (статус: {match.status})"
                await self._store.append_message(conversation_id, user_id, "user", user_message)
                message_id = await self._persist_review_failure(
                    conversation_id, user_id, command, detail
                )
                yield ErrorEvent(detail=detail)
                yield DoneEvent(message_id=message_id)
                return

            if command.role is None and playbook.roles:
                # Ask turn: never fetch section content just to discard it.
                await self._store.append_message(conversation_id, user_id, "user", user_message)
                await self._store.commit()
                ask = MessageAsk(
                    kind="review_role",
                    question=_REVIEW_ROLE_QUESTION,
                    options=playbook.roles,
                    document_id=command.document_id,
                    playbook_id=command.playbook_id,
                )
                message_id = await self._store.append_message(
                    conversation_id,
                    user_id,
                    "assistant",
                    _REVIEW_ROLE_QUESTION,
                    ask=ask.model_dump(),
                )
                await self._store.commit()
                yield AskEvent(question=_REVIEW_ROLE_QUESTION, options=playbook.roles)
                yield DoneEvent(message_id=message_id)
                return

            content = await self._documents_client.get_content(command.document_id, user_id)
        except DocumentsClientError:
            detail = "Сервис документов недоступен"
            await self._store.append_message(conversation_id, user_id, "user", user_message)
            message_id = await self._persist_review_failure(
                conversation_id, user_id, command, detail
            )
            yield ErrorEvent(detail=detail)
            yield DoneEvent(message_id=message_id)
            return
        sections = [s.model_dump() for s in content.sections]

        await self._store.append_message(conversation_id, user_id, "user", user_message)
        await self._store.commit()

        engine = ReviewEngine(
            llm=self._review_llm or self._llm,
            rag_client=self._rag,
            concurrency=self._review_concurrency,
        )
        report: ReviewReportData | None = None
        try:
            async for event in _iter_until_stop(
                engine.run(playbook, command.document_id, sections, role=command.role), stop
            ):
                if isinstance(event, ReviewReportEvent):
                    report = event.report
                yield event
        except Exception as exc:
            # T-0052: не только ReviewEngineError — обрыв LLM/сети (LLMError,
            # httpx.*) раньше пролетал мимо и оставлял осиротевшее
            # user-сообщение без записи прогона. CancelledError — BaseException
            # (3.12), поэтому стоп/дисконнект сюда не попадает и не пишется
            # как сбой.
            detail = str(exc) or exc.__class__.__name__
            logger.exception("review_run_failed", extra={"conversation_id": conversation_id})
            message_id = await self._persist_review_failure(
                conversation_id, user_id, command, detail
            )
            yield ErrorEvent(detail=detail)
            yield DoneEvent(message_id=message_id)
            return
        if (stop is not None and stop.is_set()) and report is None:
            # Частичный отчёт неделим — ничего не персистим (как при ошибке движка).
            yield DoneEvent(message_id=None, stopped=True)
            return

        assert report is not None  # engine.run always yields ReviewReportEvent before returning
        summary = _review_summary(report)
        message_id = await self._store.append_message(
            conversation_id,
            user_id,
            "assistant",
            summary,
            review=report.model_dump(mode="json"),
        )
        await self._store.commit()
        yield DoneEvent(message_id=message_id)

    async def _persist_review_failure(
        self, conversation_id: str, user_id: str, command: ReviewCommand, detail: str
    ) -> str:
        """Persist a `review_failed`-tagged assistant message for `command`.

        Assumes the user message for this turn is already persisted — either
        just before this call (the early-validation branches) or earlier in
        `run_review` (a `ReviewEngineError` mid-pipeline)."""
        ask = MessageAsk(
            kind="review_failed",
            document_id=command.document_id,
            playbook_id=command.playbook_id,
            role=command.role,
            error=detail,
        )
        message_id = await self._store.append_message(
            conversation_id, user_id, "assistant", detail, ask=ask.model_dump()
        )
        await self._store.commit()
        return message_id
