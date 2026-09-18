import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_chat_agent
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.chat.agent import ConversationNotFound
from neurolegal.agent.chat.events import (
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from neurolegal.agent.store.models import UserRow

USER_ID = "u1"


def _fake_user() -> UserRow:
    return UserRow(
        id=USER_ID,
        email="u1@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


class _FakeAgent:
    def __init__(self, *, is_new: bool = True, known: bool = True) -> None:
        self._is_new = is_new
        self._known = known
        self.last_acts: list[str] | None = None

    async def ensure_conversation(self, session_id, user_id):  # type: ignore[no-untyped-def]
        if session_id is not None and not self._known:
            raise ConversationNotFound(session_id)
        return (session_id or "new-conv-id"), self._is_new

    async def run(
        self,
        conversation_id,
        user_message,
        acts=None,
        *,
        user_id,
        profile_note=None,
        stop=None,
        template_slug=None,
    ):  # type: ignore[no-untyped-def]
        self.last_acts = acts
        yield ToolCallEvent(tool="rag_search", args={"query": "налог"})
        yield ToolResultEvent(found=[{"act": "ВК РФ", "number": "3"}])
        yield DeltaEvent(text="ВК РФ ст. 3")
        yield CitationsEvent(
            articles=[
                {
                    "act_short_name": "ВК РФ",
                    "kind": "code",
                    "number": "3",
                    "title": None,
                    "full_text": "…",
                    "score": 0.42,
                }
            ]
        )
        yield DoneEvent(message_id="msg-1")


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    name = ""
    for line in text.splitlines():
        if line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            events.append((name, json.loads(line[len("data:") :].strip())))
    return events


def test_chat_new_conversation_streams_events() -> None:
    app.dependency_overrides[get_chat_agent] = lambda: _FakeAgent(is_new=True)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.post("/chat", json={"session_id": None, "message": "Что такое налог?"})
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        names = [n for n, _ in events]
        assert names == ["session", "tool_call", "tool_result", "delta", "citations", "done"]
        assert events[0][1] == {"session_id": "new-conv-id"}
    finally:
        app.dependency_overrides.clear()


def test_chat_existing_conversation_omits_session_event() -> None:
    app.dependency_overrides[get_chat_agent] = lambda: _FakeAgent(is_new=False)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.post("/chat", json={"session_id": "abc", "message": "ещё вопрос"})
        names = [n for n, _ in _parse_sse(resp.text)]
        assert "session" not in names
        assert names[0] == "tool_call"
    finally:
        app.dependency_overrides.clear()


def test_chat_unknown_conversation_returns_404() -> None:
    app.dependency_overrides[get_chat_agent] = lambda: _FakeAgent(known=False)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.post("/chat", json={"session_id": "missing", "message": "вопрос"})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_chat_rejects_empty_message() -> None:
    app.dependency_overrides[get_chat_agent] = lambda: _FakeAgent()
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.post("/chat", json={"session_id": None, "message": ""})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_passes_selected_acts_to_agent() -> None:
    agent = _FakeAgent(is_new=True)
    app.dependency_overrides[get_chat_agent] = lambda: agent
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            tc.post("/chat", json={"session_id": None, "message": "q", "acts": ["ГК РФ"]})
        assert agent.last_acts == ["ГК РФ"]
    finally:
        app.dependency_overrides.clear()


class _SlowAgent:
    """Pauses inside `run` so two requests can be in flight at once.

    `ensure_conversation` returns instantly with a fixed id; `run` sleeps
    for 200ms so the test can fire both POSTs concurrently and have the
    second one observe the lock as held."""

    def __init__(self) -> None:
        self.runs = 0

    async def ensure_conversation(self, session_id, user_id):  # type: ignore[no-untyped-def]
        return (session_id or "conv-lock-test"), session_id is None

    async def run(
        self,
        conversation_id,
        user_message,
        acts=None,
        *,
        user_id,
        profile_note=None,
        stop=None,
        template_slug=None,
    ):  # type: ignore[no-untyped-def]
        self.runs += 1
        await asyncio.sleep(0.2)
        return
        yield  # pragma: no cover - keeps method an async generator


@pytest.mark.asyncio
async def test_concurrent_chat_on_same_conversation_returns_409() -> None:
    """Two simultaneous /chat POSTs against the same session id must not race.

    One returns 200 (and streams the response); the other returns 409 Conflict."""

    agent = _SlowAgent()
    app.dependency_overrides[get_chat_agent] = lambda: agent
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {"session_id": "conv-lock-test", "message": "q"}
            first, second = await asyncio.gather(
                client.post("/chat", json=payload),
                client.post("/chat", json=payload),
            )
    finally:
        app.dependency_overrides.clear()

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]


def test_stop_unknown_conversation_404() -> None:
    app.dependency_overrides[get_chat_agent] = lambda: _FakeAgent(known=False)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.post("/chat/nope/stop")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_stop_idle_conversation_204() -> None:
    """Ход уже завершился (события в реестре нет) — стоп идемпотентен."""
    app.dependency_overrides[get_chat_agent] = lambda: _FakeAgent(is_new=False)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.post("/chat/abc/stop")
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_stop_sets_event_and_agent_receives_it() -> None:
    """Пока ход стримится, POST stop ставит событие, переданное в agent.run.

    ВАЖНО: httpx ASGITransport прогоняет ASGI-приложение целиком до возврата
    ответа (стриминг не инкрементальный), поэтому /chat уходит фоновым
    таском; координация идёт через asyncio.Event, потому что client.stream
    здесь задедлочился бы."""
    received: dict[str, object] = {}
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingAgent(_FakeAgent):
        async def run(
            self,
            conversation_id,
            user_message,
            acts=None,
            *,
            user_id,
            profile_note=None,
            stop=None,
            template_slug=None,
        ):  # type: ignore[no-untyped-def]
            received["stop"] = stop
            started.set()
            yield DeltaEvent(text="начало ")
            await release.wait()  # держим ход открытым, пока тест не отпустит
            received["stop_was_set"] = stop is not None and stop.is_set()
            yield DoneEvent(message_id=None, stopped=True)

    app.dependency_overrides[get_chat_agent] = lambda: _BlockingAgent(is_new=False)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)

        async def scenario() -> None:
            async with AsyncClient(transport=transport, base_url="http://t") as client:
                chat_task = asyncio.create_task(
                    client.post("/chat", json={"session_id": "abc", "message": "вопрос"})
                )
                await asyncio.wait_for(started.wait(), timeout=5)
                stop_resp = await client.post("/chat/abc/stop")
                assert stop_resp.status_code == 204
                release.set()
                resp = await asyncio.wait_for(chat_task, timeout=5)
            assert resp.status_code == 200
            events = _parse_sse(resp.text)
            assert events[-1][0] == "done"
            assert events[-1][1]["stopped"] is True
            assert received["stop_was_set"] is True

        asyncio.run(scenario())
    finally:
        app.dependency_overrides.clear()
