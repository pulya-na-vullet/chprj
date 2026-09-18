"""POST /chat — Server-Sent Events streaming chat endpoint.

The DB session from `get_chat_agent` stays open for the lifetime of the SSE
generator (FastAPI tears down `yield` dependencies after the response body is
fully sent), so the agent can commit mid-stream.

A per-conversation `asyncio.Lock` enforces one in-flight turn at a time.
Concurrent POSTs return 409 Conflict. This avoids interleaved SSE streams
and complements the DB-level atomic `next_ordinal` allocation.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sse_starlette.sse import EventSourceResponse

from neurolegal.agent.api.deps import get_chat_agent
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.chat.agent import ChatAgent, ConversationNotFound
from neurolegal.agent.chat.events import ErrorEvent, SessionEvent
from neurolegal.agent.chat.prompts import build_profile_note
from neurolegal.agent.store.models import UserRow
from neurolegal.contracts import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# Process-wide registry; each conversation has its own lock so two requests
# against different conversations never block each other. Entries are removed
# in event_stream's finally block to prevent unbounded growth.
#
# WARNING: in-process only. Multi-worker uvicorn deployments lose this
# guarantee — each worker has its own dict. A future shared mechanism
# (Postgres advisory lock, Redis SETNX) would be needed for horizontal scale.
_turn_locks: dict[str, asyncio.Lock] = {}

# Stop-события живут ровно столько, сколько ход: created before streaming,
# removed in event_stream's finally. Тот же in-process caveat, что и
# _turn_locks (multi-worker деплой потребует общего механизма).
_stop_events: dict[str, asyncio.Event] = {}


def _lock_for(conversation_id: str) -> asyncio.Lock:
    lock = _turn_locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _turn_locks[conversation_id] = lock
    return lock


@router.post("/chat")
async def chat(
    req: ChatRequest,
    agent: Annotated[ChatAgent, Depends(get_chat_agent)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> EventSourceResponse:
    try:
        conversation_id, is_new = await agent.ensure_conversation(req.session_id, user.id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc

    lock = _lock_for(conversation_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="turn already in progress")
    # Acquire synchronously: we just observed locked() is False, and CPython's
    # asyncio.Lock.acquire() returns without suspending when uncontended. No
    # await between locked() and acquire() means no other coroutine can race
    # in. Release happens in event_stream's finally, after the SSE body is
    # fully sent.
    await lock.acquire()
    stop_event = asyncio.Event()
    _stop_events[conversation_id] = stop_event

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            if is_new:
                ev = SessionEvent(session_id=conversation_id)
                yield {"event": ev.event, "data": json.dumps(ev.data, ensure_ascii=False)}
            try:
                gen = (
                    agent.run_review(
                        conversation_id, req.command, req.message, user_id=user.id, stop=stop_event
                    )
                    if req.command is not None
                    else agent.run(
                        conversation_id,
                        req.message,
                        req.acts,
                        user_id=user.id,
                        profile_note=build_profile_note(user),
                        stop=stop_event,
                        template_slug=req.template_slug,
                    )
                )
                async for agent_event in gen:
                    yield {
                        "event": agent_event.event,
                        "data": json.dumps(agent_event.data, ensure_ascii=False),
                    }
            except Exception as exc:
                logger.exception("chat_stream_failed")
                err = ErrorEvent(detail=str(exc))
                yield {
                    "event": err.event,
                    "data": json.dumps(err.data, ensure_ascii=False),
                }
        finally:
            _stop_events.pop(conversation_id, None)
            lock.release()
            # Prune the registry entry; no waiters can exist because concurrent
            # requests are rejected with 409 above rather than queued.
            _turn_locks.pop(conversation_id, None)

    return EventSourceResponse(event_stream())


@router.post("/chat/{conversation_id}/stop", status_code=204)
async def stop_chat(
    conversation_id: str,
    agent: Annotated[ChatAgent, Depends(get_chat_agent)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Response:
    """Кооперативная остановка текущего хода. Идемпотентен: 204 и когда
    ход уже завершился. 404 — чужая или несуществующая беседа (наружу не
    различаем)."""
    try:
        await agent.ensure_conversation(conversation_id, user.id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    event = _stop_events.get(conversation_id)
    if event is not None:
        event.set()
    return Response(status_code=204)
