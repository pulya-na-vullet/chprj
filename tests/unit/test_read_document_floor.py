"""Regression: a successful read_document keeps the LEGAL safety floor from
overwriting a document-grounded answer.

This is an adaptation of the pre-Phase-B test at git commit c4157f7
(`test_legal_floor_not_applied_when_document_was_read` in the old
`tests/unit/test_read_document_tool.py`), which was dropped when documents
moved to the hub service. Documents now live in neurolegal-documents-api,
so this test drives ChatAgent with a fake DocumentsClient (list_for_conversation
+ get_content) instead of the removed DocumentStore.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.chat.answers import NO_BASIS_NOTE, SEARCH_UNAVAILABLE_NOTE
from neurolegal.agent.chat.intent import Intent
from neurolegal.agent.llm.types import TextChunk, ToolCallRequest
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.contracts import HubDocumentContent, HubDocumentInfo, HubSection

USER_ID = "u1"

SECTIONS = [
    HubSection(number="1", title="Предмет", text="1. Предмет\nТекст.", level=1, start=0, end=10),
    HubSection(number="2", title="Оплата", text="2. Оплата\n10 дней.", level=1, start=10, end=20),
]


class _FakeDocsClient:
    """One ready document attached to a single conversation."""

    def __init__(self, doc_id: str) -> None:
        self._doc_id = doc_id

    async def list_for_conversation(
        self, conversation_id: str, user_id: str
    ) -> list[HubDocumentInfo]:
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
        return HubDocumentContent(
            id=document_id,
            status="ready",
            full_text="1. Предмет\nТекст.\n2. Оплата\n10 дней.",
            sections=SECTIONS,
        )


class _ScriptedLLM:
    """Yields a scripted sequence per stream() call (one call per tool loop)."""

    def __init__(self, script: list[list[object]]) -> None:
        self._script = list(script)

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        for ev in self._script.pop(0):
            yield ev


@pytest_asyncio.fixture
async def store():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield ConversationStore(s)
    await engine.dispose()


async def _drain(it: AsyncIterator) -> None:
    async for _ in it:
        pass


@pytest.mark.asyncio
async def test_legal_floor_not_applied_when_document_was_read(store):
    """A LEGAL turn that read an uploaded document (no RAG articles) must keep
    the model's answer — the safety floor must not overwrite it with NO_BASIS."""
    doc_id = "d1"
    llm = _ScriptedLLM(
        [
            [ToolCallRequest(id="t1", name="read_document", arguments={"document_id": doc_id})],
            [TextChunk(text="Срок оплаты — 10 дней.")],
        ]
    )
    agent = ChatAgent(
        llm=llm,  # type: ignore[arg-type]
        rag_client=object(),  # type: ignore[arg-type]
        store=store,
        documents_client=_FakeDocsClient(doc_id),  # type: ignore[arg-type]
        classify_intent=lambda _m: Intent.LEGAL,
    )
    cid = await store.create_conversation(USER_ID)
    await store.commit()
    await _drain(agent.run(cid, "Какой срок оплаты в договоре?", user_id=USER_ID))
    history = await store.load_history(cid, USER_ID)

    answer = history[-1].content
    assert "10 дней" in answer
    assert NO_BASIS_NOTE not in answer
    assert SEARCH_UNAVAILABLE_NOTE not in answer
