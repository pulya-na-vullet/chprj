"""Tests for ChatAgent.run_review: the risk_review slash command.

Follows the SQLite-session pattern from test_read_document_tool.py and the
FakeLLM/_tc pattern from test_review_engine.py, but drives the command
through ChatAgent (not ReviewEngine directly) to exercise validation,
persistence, and the markdown summary end to end.

Documents live in the hub service now (neurolegal-documents-api), so this
test drives ChatAgent with a fake documents client rather than the removed
DocumentStore.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.chat.events import AskEvent, DoneEvent, ErrorEvent, ReviewReportEvent
from neurolegal.agent.llm.client import LLMError
from neurolegal.agent.llm.types import ChatMessage, LLMEvent, TextChunk, ToolCallRequest, ToolSpec
from neurolegal.agent.review.playbook import Playbook
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.contracts import HubDocumentContent, HubDocumentInfo, HubSection, ReviewCommand

USER_ID = "u1"

SECTIONS: list[dict[str, object]] = [
    {
        "number": "1",
        "title": "Оплата",
        "text": "1. Оплата в течение 30 дней с даты подписания.",
        "level": 1,
        "start": 0,
        "end": 40,
    },
]

PLAYBOOK = Playbook.model_validate(
    {
        "id": "mini",
        "name": "Мини",
        "rules": [
            {"id": "pay", "title": "Оплата", "question": "Срок оплаты зафиксирован?"},
        ],
    }
)

# T-0046: playbook with declared roles, for the ask/role-interception tests.
PLAYBOOK_WITH_ROLES = Playbook.model_validate(
    {
        "id": "mini_roles",
        "name": "Мини с ролями",
        "roles": ["Заказчик", "Исполнитель"],
        "rules": [
            {"id": "pay", "title": "Оплата", "question": "Срок оплаты зафиксирован?"},
        ],
    }
)


def _tc(name: str, args: dict[str, object]) -> ToolCallRequest:
    return ToolCallRequest(id="x", name=name, arguments=args)


class FakeReviewLLM:
    """Queue of scripted responses; each entry is a list of LLMEvent."""

    def __init__(self, scripted: list[list[LLMEvent]]) -> None:
        self._scripted = list(scripted)
        self.calls: list[tuple[list[ChatMessage], list[ToolSpec]]] = []

    async def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append((messages, tools))
        for ev in self._scripted.pop(0):
            yield ev


class FakeDocsClient:
    """Stands in for DocumentsClient: one doc, attached to a single conversation."""

    def __init__(self, attached_conversation_id: str, doc_id: str) -> None:
        self._attached_conversation_id = attached_conversation_id
        self._doc_id = doc_id
        self.get_content_calls = 0

    async def list_for_conversation(
        self, conversation_id: str, user_id: str
    ) -> list[HubDocumentInfo]:
        if conversation_id != self._attached_conversation_id:
            return []
        return [
            HubDocumentInfo(
                id=self._doc_id,
                owner_id="default",
                filename="договор.docx",
                content_type="application/octet-stream",
                size=10,
                status="ready",
                parser="docx",
                page_count=None,
                error=None,
                created_at=datetime.now(UTC),
            )
        ]

    async def get_content(self, document_id: str, user_id: str) -> HubDocumentContent:
        self.get_content_calls += 1
        return HubDocumentContent(
            id=document_id,
            status="ready",
            full_text="1. Оплата в течение 30 дней с даты подписания.",
            sections=[HubSection(**s) for s in SECTIONS],  # type: ignore[arg-type]
        )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


async def test_run_review_persists_report(engine: AsyncEngine) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        # map -> section "1" mapped to rule "pay"; assess -> status "ok" (no
        # risk). The rule has no rag_queries, so grounding/judge never run —
        # rag_client is never called for this scenario.
        review_llm = FakeReviewLLM(
            [
                [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
                [
                    _tc(
                        "assess_rule",
                        {"status": "ok", "explanation": "Срок закреплён и не зависит от условий"},
                    )
                ],
            ]
        )
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]  # unused: run_review prefers review_llm
            rag_client=object(),  # type: ignore[arg-type]  # unused: no rag_queries, no risk
            store=conv_store,
            documents_client=FakeDocsClient(conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK.id: PLAYBOOK},
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        # role set: skips the T-0046 ask branch and runs the pipeline directly.
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK.id, role="Заказчик"
        )
        user_message = 'Проверить договор "договор.docx" по плейбуку Мини'

        events = [
            ev async for ev in agent.run_review(conv_id, command, user_message, user_id=USER_ID)
        ]

        assert any(isinstance(e, ReviewReportEvent) for e in events)
        report_event = next(e for e in events if isinstance(e, ReviewReportEvent))
        assert report_event.report.role == "Заказчик"
        done = next(e for e in events if isinstance(e, DoneEvent))
        assert done.message_id

        history = await conv_store.load_history(conv_id, USER_ID)
        assert len(history) == 2
        assert history[0].role == "user" and history[0].content == user_message
        assert history[-1].role == "assistant"
        assert history[-1].review is not None
        assert history[-1].review["coverage"][0]["status"] == "ok"


async def test_run_review_stopped_before_engine_persists_nothing(engine: AsyncEngine) -> None:
    """Стоп, выставленный до запуска движка: engine.run не должен успеть дать
    отчёт. DoneEvent несёт stopped=True и message_id=None; в истории беседы
    остаётся только сообщение пользователя (partial report is indivisible —
    nothing is persisted, same as an engine error)."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        review_llm = FakeReviewLLM(
            [
                [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
                [
                    _tc(
                        "assess_rule",
                        {"status": "ok", "explanation": "Срок закреплён и не зависит от условий"},
                    )
                ],
            ]
        )
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]  # unused: run_review prefers review_llm
            rag_client=object(),  # type: ignore[arg-type]  # unused: no rag_queries, no risk
            store=conv_store,
            documents_client=FakeDocsClient(conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK.id: PLAYBOOK},
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        # role set: skips the T-0046 ask branch and reaches the engine, so the
        # stop actually lands before the engine yields anything.
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK.id, role="Заказчик"
        )
        user_message = 'Проверить договор "договор.docx" по плейбуку Мини'

        stop = asyncio.Event()
        stop.set()  # стоп до старта движка

        events = [
            ev
            async for ev in agent.run_review(
                conv_id, command, user_message, user_id=USER_ID, stop=stop
            )
        ]

        assert not any(isinstance(e, ReviewReportEvent) for e in events)
        done = events[-1]
        assert isinstance(done, DoneEvent)
        assert done.stopped is True
        assert done.message_id is None

        history = await conv_store.load_history(conv_id, USER_ID)
        assert len(history) == 1
        assert history[0].role == "user"
        assert history[0].content == user_message


async def test_run_review_wrong_conversation_rejected(engine: AsyncEngine) -> None:
    """T-0046: an early validation failure (document not found in this
    conversation) now persists both the user message and a `review_failed`
    assistant message, so the conversation history stays whole."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        other_conv_id = await conv_store.create_conversation(USER_ID)
        this_conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=FakeDocsClient(other_conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK.id: PLAYBOOK},
        )
        command = ReviewCommand(type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK.id)
        user_message = "Проверить договор"

        events = [
            ev
            async for ev in agent.run_review(this_conv_id, command, user_message, user_id=USER_ID)
        ]

        assert len(events) == 2
        assert isinstance(events[0], ErrorEvent)
        assert events[0].detail == "Документ не найден в этой беседе"
        assert isinstance(events[1], DoneEvent)
        assert events[1].message_id

        history = await conv_store.load_history(this_conv_id, USER_ID)
        assert len(history) == 2
        assert history[0].role == "user" and history[0].content == user_message
        assert history[1].role == "assistant"
        assert history[1].content == events[0].detail
        assert history[1].ask is not None
        assert history[1].ask["kind"] == "review_failed"
        assert history[1].ask["error"] == events[0].detail
        assert history[1].ask["document_id"] == doc_id
        assert history[1].ask["playbook_id"] == PLAYBOOK.id


async def test_run_review_without_role_asks_for_role(engine: AsyncEngine) -> None:
    """T-0046: a risk_review command with no `role` pauses instead of running
    the pipeline — persists an `ask` assistant message with the playbook's
    roles as options, emits AskEvent, and never calls the review LLM."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        review_llm = FakeReviewLLM([])  # engine must never be invoked
        docs_client = FakeDocsClient(conv_id, doc_id)
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=docs_client,  # type: ignore[arg-type]
            playbooks={PLAYBOOK_WITH_ROLES.id: PLAYBOOK_WITH_ROLES},
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK_WITH_ROLES.id
        )
        user_message = 'Проверить договор "договор.docx" по плейбуку Мини с ролями'

        events = [
            ev async for ev in agent.run_review(conv_id, command, user_message, user_id=USER_ID)
        ]

        assert not any(isinstance(e, ReviewReportEvent) for e in events)
        ask_events = [e for e in events if isinstance(e, AskEvent)]
        assert len(ask_events) == 1
        assert ask_events[0].options == ["Заказчик", "Исполнитель"]
        done = next(e for e in events if isinstance(e, DoneEvent))
        assert done.message_id
        assert review_llm.calls == []  # the engine was never called
        # M1: an ask turn must never fetch section content it discards.
        assert docs_client.get_content_calls == 0

        history = await conv_store.load_history(conv_id, USER_ID)
        assert len(history) == 2
        assert history[0].role == "user" and history[0].content == user_message
        assert history[1].role == "assistant"
        assert history[1].ask is not None
        assert history[1].ask["kind"] == "review_role"
        assert history[1].ask["options"] == ["Заказчик", "Исполнитель"]
        assert history[1].ask["document_id"] == doc_id
        assert history[1].ask["playbook_id"] == PLAYBOOK_WITH_ROLES.id


async def test_run_review_roleless_playbook_runs_without_asking(engine: AsyncEngine) -> None:
    """T-0070: a playbook with `roles == []` (service documents) never
    triggers the review_role ask, even when `command.role` is None — the
    pipeline runs directly, same as if a role had been supplied."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        review_llm = FakeReviewLLM(
            [
                [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
                [
                    _tc(
                        "assess_rule",
                        {"status": "ok", "explanation": "Срок закреплён и не зависит от условий"},
                    )
                ],
            ]
        )
        docs_client = FakeDocsClient(conv_id, doc_id)
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=docs_client,  # type: ignore[arg-type]
            playbooks={PLAYBOOK.id: PLAYBOOK},  # PLAYBOOK.roles == []
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        # role deliberately omitted: PLAYBOOK declares no roles, so the ask
        # branch must not fire.
        command = ReviewCommand(type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK.id)
        user_message = 'Проверить документ "договор.docx" по плейбуку Мини'

        events = [
            ev async for ev in agent.run_review(conv_id, command, user_message, user_id=USER_ID)
        ]

        assert not any(isinstance(e, AskEvent) for e in events)
        assert any(isinstance(e, ReviewReportEvent) for e in events)
        report_event = next(e for e in events if isinstance(e, ReviewReportEvent))
        assert report_event.report.role is None
        done = next(e for e in events if isinstance(e, DoneEvent))
        assert done.message_id
        assert docs_client.get_content_calls == 1

        history = await conv_store.load_history(conv_id, USER_ID)
        assert len(history) == 2
        assert history[0].role == "user" and history[0].content == user_message
        assert history[-1].role == "assistant"
        assert history[-1].ask is None


async def test_run_intercepts_pending_ask_and_delegates_to_review(engine: AsyncEngine) -> None:
    """T-0046: once run_review has asked for the role, the next plain `run()`
    turn is treated as the answer — ChatAgent.run delegates to run_review
    with the role filled in, and the user message is persisted exactly
    once (inside run_review, not duplicated by run())."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        review_llm = FakeReviewLLM([])  # no engine call for the ask turn
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]  # unused: both turns route to run_review
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=FakeDocsClient(conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK_WITH_ROLES.id: PLAYBOOK_WITH_ROLES},
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK_WITH_ROLES.id
        )
        ask_events = [
            ev
            async for ev in agent.run_review(conv_id, command, "Проверить договор", user_id=USER_ID)
        ]
        assert any(isinstance(e, AskEvent) for e in ask_events)

        # Script the pipeline for the follow-up turn.
        review_llm._scripted = [
            [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
            [_tc("assess_rule", {"status": "ok", "explanation": "Срок закреплён"})],
        ]

        run_events = [ev async for ev in agent.run(conv_id, "Заказчик", user_id=USER_ID)]

        report_event = next(e for e in run_events if isinstance(e, ReviewReportEvent))
        assert report_event.report.role == "Заказчик"
        # map + assess + резюме (T-0047) — engine really ran
        assert len(review_llm.calls) == 3

        history = await conv_store.load_history(conv_id, USER_ID)
        # user(ask-command), assistant(ask), user(role reply), assistant(report)
        assert len(history) == 4
        assert history[2].role == "user" and history[2].content == "Заказчик"
        assert history[3].role == "assistant" and history[3].review is not None


async def test_run_pending_ask_whitespace_reply_falls_through_to_normal_run(
    engine: AsyncEngine,
) -> None:
    """M2: a whitespace-only reply to the pending role question is not an
    answer — ChatAgent.run must not intercept it into run_review (which
    would start a review with role=""); instead it falls through to the
    normal run() path, exactly as if there were no pending ask."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        review_llm = FakeReviewLLM([])  # the review engine must never be invoked
        chat_llm = FakeReviewLLM([[TextChunk(text="Уточните, пожалуйста, вопрос.")]])
        agent = ChatAgent(
            llm=chat_llm,  # type: ignore[arg-type]
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=FakeDocsClient(conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK_WITH_ROLES.id: PLAYBOOK_WITH_ROLES},
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK_WITH_ROLES.id
        )
        ask_events = [
            ev
            async for ev in agent.run_review(conv_id, command, "Проверить договор", user_id=USER_ID)
        ]
        assert any(isinstance(e, AskEvent) for e in ask_events)

        run_events = [ev async for ev in agent.run(conv_id, "   ", user_id=USER_ID)]

        assert not any(isinstance(e, ReviewReportEvent) for e in run_events)
        assert review_llm.calls == []  # pending ask was NOT re-entered into run_review
        assert chat_llm.calls  # the normal run() loop actually called the chat LLM
        done = next(e for e in run_events if isinstance(e, DoneEvent))
        assert done.message_id

        history = await conv_store.load_history(conv_id, USER_ID)
        # user(ask-command), assistant(ask), user("   "), assistant(normal reply)
        assert len(history) == 4
        assert history[2].role == "user" and history[2].content == "   "
        assert history[3].role == "assistant"
        assert history[3].ask is None
        assert history[3].review is None


async def test_run_review_engine_error_persists_failed_message(engine: AsyncEngine) -> None:
    """T-0046: a ReviewEngineError mid-pipeline persists a `review_failed`
    assistant message (role + error), in addition to ErrorEvent + DoneEvent."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"

        # Map stage never returns a valid tool call, even after the retry —
        # ReviewEngine._structured raises ReviewEngineError.
        review_llm = FakeReviewLLM([[TextChunk(text="болтовня")], [TextChunk(text="опять")]])
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=FakeDocsClient(conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK.id: PLAYBOOK},
            review_llm=review_llm,  # type: ignore[arg-type]
        )
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK.id, role="Заказчик"
        )
        user_message = "Проверить договор"

        events = [
            ev async for ev in agent.run_review(conv_id, command, user_message, user_id=USER_ID)
        ]

        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        done = next(e for e in events if isinstance(e, DoneEvent))
        assert done.message_id
        assert done.stopped is False

        history = await conv_store.load_history(conv_id, USER_ID)
        assert len(history) == 2
        assert history[0].role == "user" and history[0].content == user_message
        assert history[1].role == "assistant"
        assert history[1].content == error_events[0].detail
        assert history[1].ask is not None
        assert history[1].ask["kind"] == "review_failed"
        assert history[1].ask["role"] == "Заказчик"
        assert history[1].ask["error"] == error_events[0].detail


async def test_run_review_llm_error_persists_failed_message(engine: AsyncEngine) -> None:
    """T-0052: обрыв LLM (LLMError/сеть) — не только ReviewEngineError —
    тоже персистится как review_failed: иначе прогон исчезал из /reviews,
    оставляя осиротевшее user-сообщение."""

    class ExplodingLLM:
        async def stream(
            self, messages: list[ChatMessage], tools: list[ToolSpec]
        ) -> AsyncIterator[LLMEvent]:
            raise LLMError("OpenRouter connection reset")
            yield  # pragma: no cover — делает функцию генератором

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        conv_store = ConversationStore(session)
        conv_id = await conv_store.create_conversation(USER_ID)
        await conv_store.commit()
        doc_id = "doc-1"
        agent = ChatAgent(
            llm=object(),  # type: ignore[arg-type]
            rag_client=object(),  # type: ignore[arg-type]
            store=conv_store,
            documents_client=FakeDocsClient(conv_id, doc_id),  # type: ignore[arg-type]
            playbooks={PLAYBOOK.id: PLAYBOOK},
            review_llm=ExplodingLLM(),  # type: ignore[arg-type]
        )
        command = ReviewCommand(
            type="risk_review", document_id=doc_id, playbook_id=PLAYBOOK.id, role="Заказчик"
        )

        events = [
            ev async for ev in agent.run_review(conv_id, command, "Проверить", user_id=USER_ID)
        ]

        assert any(isinstance(e, ErrorEvent) for e in events)
        done = next(e for e in events if isinstance(e, DoneEvent))
        assert done.message_id

        history = await conv_store.load_history(conv_id, USER_ID)
        assert history[-1].ask is not None
        assert history[-1].ask["kind"] == "review_failed"
        assert "OpenRouter" in str(history[-1].ask["error"])
