"""Conversation history endpoints for the sidebar: list, load, delete."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from neurolegal.agent.api.deps import get_store
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import UserRow
from neurolegal.contracts import (
    ConversationOut,
    ConversationsResponse,
    MessageOut,
    MessagesResponse,
)

router = APIRouter()


@router.get("/conversations", response_model=ConversationsResponse)
async def list_conversations(
    store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> ConversationsResponse:
    items = await store.list_conversations(user.id)
    return ConversationsResponse(
        conversations=[
            ConversationOut(
                id=c.id, title=c.title, updated_at=c.updated_at.isoformat(), preview=c.preview
            )
            for c in items
        ]
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessagesResponse)
async def get_messages(
    conversation_id: str,
    store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> MessagesResponse:
    if not await store.conversation_exists(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="conversation not found")
    history = await store.load_history(conversation_id, user.id)
    return MessagesResponse(
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=m.citations,
                web_sources=m.web_sources,
                review=m.review,
                created_at=m.created_at.isoformat(),
                stopped=m.stopped,
                ask=m.ask,
                template_draft=m.template_draft,
                template_doc=m.template_doc,
            )
            for m in history
        ]
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Response:
    deleted = await store.delete_conversation(conversation_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    await store.commit()
    return Response(status_code=204)
