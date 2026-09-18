"""Сквозной контракт SSE в POST /chat — на замоканном LLM (T-0103, пункт 5).

Единственная сквозная проверка контракта событий жила в
test_chat_endpoint.py под маркером `e2e`: ей нужны были и живая БД
(накатанные миграции), и платный OPENROUTER_API_KEY — поэтому она не
выполнялась никогда. Здесь тот же контракт проверяется через полное приложение (роут,
блокировка хода, sse_starlette, сериализация событий), но LLM и хранилище
подменены: нужен только Python.

Проверяется именно порядок и состав кадров, которые увидит браузер:
`session` первым и только на новой беседе, `done` последним, `citations`
присутствует, и текст ответа приезжает дельтами.
"""

import json
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_chat_agent
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.llm.types import LLMEvent, TextChunk, ToolCallRequest
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base, UserRow
from neurolegal.contracts import SearchedArticle

pytestmark = pytest.mark.api_with_mocks

USER_ID = "u-sse"


def _article() -> SearchedArticle:
    return SearchedArticle(
        article_id="11111111-1111-4111-8111-111111111111",
        act_short_name="ВК РФ",
        act_kind="codex",
        number="3",
        title="Основные принципы",
        full_text="Основные принципы водного законодательства.",
        matched_chunks=[],
        score=0.42,
    )


class _ScriptedLLM:
    """Первый ход: инструмент → ответ. Второй: сразу ответ."""

    def __init__(self) -> None:
        self._script: list[list[LLMEvent]] = [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "принципы"})],
            [TextChunk(text="Согласно "), TextChunk(text="ст. 3 ВК РФ...")],
            [TextChunk(text="Их устанавливает закон.")],
        ]
        self.calls = 0

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        events = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        for event in events:
            yield event


class _StubRag:
    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        return [_article()]


def _user() -> UserRow:
    from datetime import UTC, datetime

    return UserRow(
        id=USER_ID,
        email="sse@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield ConversationStore(session)
    await engine.dispose()


@pytest.fixture
def client(store: ConversationStore) -> Iterator[TestClient]:
    agent = ChatAgent(llm=_ScriptedLLM(), rag_client=_StubRag(), store=store)
    app.dependency_overrides[get_chat_agent] = lambda: agent
    app.dependency_overrides[get_current_user] = _user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _frames(body: str) -> list[tuple[str, str]]:
    """(имя события, data) в порядке прихода."""
    out: list[tuple[str, str]] = []
    name: str | None = None
    for line in body.splitlines():
        if line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:") and name is not None:
            out.append((name, line[len("data:") :].strip()))
            name = None
    return out


def test_sse_contract_across_two_turns(client: TestClient) -> None:
    first = client.post(
        "/chat",
        json={"session_id": None, "message": "Какие принципы водного законодательства?"},
    )
    assert first.status_code == 200

    frames = _frames(first.text)
    names = [n for n, _ in frames]
    assert names[0] == "session", names
    assert names[-1] == "done", names
    assert "citations" in names
    assert "tool_call" in names and "tool_result" in names

    session_id = json.loads(frames[0][1])["session_id"]
    assert isinstance(session_id, str) and session_id

    # Текст ответа приезжает дельтами и собирается в то, что увидит пользователь.
    answer = "".join(json.loads(d)["text"] for n, d in frames if n == "delta")
    assert answer == "Согласно ст. 3 ВК РФ..."

    cited = json.loads(next(d for n, d in frames if n == "citations"))["articles"]
    assert [c["number"] for c in cited] == ["3"]

    # Второй ход по той же беседе: `session` не переизлучается.
    second = client.post("/chat", json={"session_id": session_id, "message": "А кто их ставит?"})
    assert second.status_code == 200
    names2 = [n for n, _ in _frames(second.text)]
    assert "session" not in names2
    assert names2[-1] == "done"


def test_unknown_conversation_is_404(client: TestClient) -> None:
    resp = client.post("/chat", json={"session_id": "no-such-conversation", "message": "привет"})
    assert resp.status_code == 404
