"""Agent document endpoints — thin proxies to the documents hub + conversation
attachment. The hub owns storage/extraction; the agent owns conversations."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from fastapi.responses import RedirectResponse

from neurolegal.agent.api.deps import get_documents_client, get_playbooks, get_store
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.review.playbook import Playbook
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.documents_client import (
    DocumentsClient,
    DocumentsClientError,
    DocumentsNotFoundError,
)
from neurolegal.contracts import (
    AttachLibraryRequest,
    HubDocumentContent,
    HubDocumentInfo,
    HubDocumentListResponse,
    PlaybookInfo,
    PlaybooksResponse,
    UploadResponse,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_ALLOWED = {".docx", ".pdf"}
_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


async def _read_capped(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="Файл больше 20 МБ")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/documents")
async def upload_document(
    file: UploadFile,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    conv_store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
    session_id: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=422, detail="Поддерживаются только файлы .docx и .pdf")
    data = await _read_capped(file)

    # Upload to the hub first — it doesn't need a conversation id. This way a
    # hub failure never leaves behind a titleless orphan conversation.
    try:
        info = await docs.upload(
            data, file.filename or f"file{suffix}", _CONTENT_TYPES[suffix], owner_id=user.id
        )
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc

    if session_id is None:
        conversation_id = await conv_store.create_conversation(user.id)
        await conv_store.commit()
    else:
        if not await conv_store.conversation_exists(session_id, user.id):
            raise HTTPException(status_code=404, detail="conversation not found")
        conversation_id = session_id

    try:
        attached = await docs.attach(info.id, conversation_id, user.id)
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc
    return UploadResponse(document=attached, session_id=conversation_id)


@router.get("/library/documents")
async def library_documents(
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> HubDocumentListResponse:
    try:
        rows = await docs.list_for_owner(user.id)
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc
    return HubDocumentListResponse(documents=rows)


@router.post("/library/documents")
async def library_upload(
    file: UploadFile,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> HubDocumentInfo:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=422, detail="Поддерживаются только файлы .docx и .pdf")
    data = await _read_capped(file)
    try:
        return await docs.upload(
            data, file.filename or f"file{suffix}", _CONTENT_TYPES[suffix], owner_id=user.id
        )
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc


@router.post("/library/documents/{document_id}/attach")
async def library_attach(
    document_id: str,
    body: AttachLibraryRequest,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    conv_store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> UploadResponse:
    """Attach an existing library document to a conversation (created when
    session_id is empty) — the «спросить по выбранным» flow of the Files screen."""
    try:
        info = await docs.get_info(document_id, user.id)
    except DocumentsNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc

    if body.session_id is None:
        conversation_id = await conv_store.create_conversation(user.id)
        await conv_store.commit()
    else:
        if not await conv_store.conversation_exists(body.session_id, user.id):
            raise HTTPException(status_code=404, detail="conversation not found")
        conversation_id = body.session_id

    try:
        attached = await docs.attach(info.id, conversation_id, user.id)
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc
    return UploadResponse(document=attached, session_id=conversation_id)


@router.delete("/library/documents/{document_id}", status_code=204)
async def library_delete(
    document_id: str,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Response:
    try:
        await docs.delete(document_id, user.id)
    except DocumentsNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc
    return Response(status_code=204)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> HubDocumentInfo:
    try:
        return await docs.get_info(document_id, user.id)
    except DocumentsNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc


@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: str,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> HubDocumentContent:
    try:
        return await docs.get_content(document_id, user.id)
    except DocumentsNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc


@router.get("/conversations/{conversation_id}/documents")
async def conversation_documents(
    conversation_id: str,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> HubDocumentListResponse:
    try:
        rows = await docs.list_for_conversation(conversation_id, user.id)
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc
    return HubDocumentListResponse(documents=rows)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    docs: Annotated[DocumentsClient, Depends(get_documents_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> RedirectResponse:
    try:
        location = await docs.download_location(document_id, user.id)
    except DocumentsNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except DocumentsClientError as exc:
        raise HTTPException(status_code=502, detail="Сервис документов недоступен") from exc
    if location is None:
        raise HTTPException(status_code=410, detail="Оригинал документа недоступен")
    return RedirectResponse(location, status_code=307)


@router.get("/playbooks")
async def playbooks(
    pbs: Annotated[dict[str, Playbook], Depends(get_playbooks)],
) -> PlaybooksResponse:
    return PlaybooksResponse(
        playbooks=[
            PlaybookInfo(id=p.id, name=p.name, rules_count=len(p.rules), roles=p.roles)
            for p in pbs.values()
        ]
    )
