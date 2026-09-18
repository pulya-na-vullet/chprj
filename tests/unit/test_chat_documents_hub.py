"""ChatAgent uses the hub client: ready docs surface read_document + prompt line."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.chat.intent import Intent
from neurolegal.agent.llm.types import TextChunk
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.agent.tools.documents_client import DocumentsClientError
from neurolegal.contracts import HubDocumentInfo

USER_ID = "u1"


def _info(status: str) -> HubDocumentInfo:
    from datetime import UTC, datetime

    return HubDocumentInfo(
        id="d1",
        owner_id="default",
        filename="c.docx",
        content_type="application/octet-stream",
        size=10,
        status=status,
        parser="docx",
        page_count=None,
        error=None,
        created_at=datetime.now(UTC),
    )


class _FakeDocsClient:
    def __init__(self, docs):
        self._docs = docs

    async def list_for_conversation(self, conversation_id, user_id):
        return self._docs


class _BoomingDocsClient:
    """Hub is down: every call raises DocumentsClientError."""

    async def list_for_conversation(self, conversation_id, user_id):
        raise DocumentsClientError("hub unreachable")


class _CapturingLLM:
    """Records the tool specs it was offered, then returns a trivial answer."""

    def __init__(self):
        self.seen_tools: list[str] = []

    async def stream(self, messages, tools=None, **kwargs):
        self.seen_tools = [t.name for t in (tools or [])]
        self.system = messages[0].content
        yield TextChunk(text="ок")

    def __call__(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


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
async def test_ready_doc_exposes_read_document(store):
    llm = _CapturingLLM()
    agent = ChatAgent(
        llm=llm,  # type: ignore[arg-type]
        rag_client=None,  # type: ignore[arg-type]
        store=store,
        documents_client=_FakeDocsClient([_info("ready")]),  # type: ignore[arg-type]
        classify_intent=lambda _m: Intent.TEXT_TASK,
    )
    cid = await store.create_conversation(USER_ID)
    await store.commit()
    await _drain(agent.run(cid, "перескажи документ", user_id=USER_ID))
    assert "read_document" in llm.seen_tools
    assert "id=d1" in llm.system


@pytest.mark.asyncio
async def test_processing_doc_is_hidden(store):
    llm = _CapturingLLM()
    agent = ChatAgent(
        llm=llm,  # type: ignore[arg-type]
        rag_client=None,  # type: ignore[arg-type]
        store=store,
        documents_client=_FakeDocsClient([_info("processing")]),  # type: ignore[arg-type]
        classify_intent=lambda _m: Intent.TEXT_TASK,
    )
    cid = await store.create_conversation(USER_ID)
    await store.commit()
    await _drain(agent.run(cid, "привет", user_id=USER_ID))
    assert "read_document" not in llm.seen_tools


@pytest.mark.asyncio
async def test_hub_outage_degrades_to_no_documents(store):
    """A documents-hub outage must not crash the chat turn: run() should
    complete normally with no documents (no read_document tool offered)."""
    llm = _CapturingLLM()
    agent = ChatAgent(
        llm=llm,  # type: ignore[arg-type]
        rag_client=None,  # type: ignore[arg-type]
        store=store,
        documents_client=_BoomingDocsClient(),  # type: ignore[arg-type]
        classify_intent=lambda _m: Intent.TEXT_TASK,
    )
    cid = await store.create_conversation(USER_ID)
    await store.commit()
    await _drain(agent.run(cid, "привет", user_id=USER_ID))  # must not raise DocumentsClientError
    assert "read_document" not in llm.seen_tools
    history = await store.load_history(cid, USER_ID)
    assert history[-1].content == "ок"
