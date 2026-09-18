"""Documents hub HTTP routes."""

import asyncio
import hashlib
from collections.abc import Coroutine
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.exc import IntegrityError

from neurolegal.contracts import (
    AttachRequest,
    HubDocumentContent,
    HubDocumentInfo,
    HubDocumentListResponse,
    HubSection,
)
from neurolegal.documents.api.deps import (
    get_blob_store,
    get_session_factory,
    get_store,
)
from neurolegal.documents.config import (
    ALLOWED_SUFFIXES,
    MAX_UPLOAD_BYTES,
    UPLOAD_CHUNK_BYTES,
)
from neurolegal.documents.store.blob import BlobStore
from neurolegal.documents.store.document_store import DocumentStore
from neurolegal.documents.store.models import HubDocument
from neurolegal.documents.worker import run_extraction

router = APIRouter()

# asyncio.create_task() only holds a weak reference to the scheduled task; with
# nothing else referencing it, the task can be garbage-collected mid-run before
# it completes (see the "Important" note on asyncio.create_task in the stdlib
# docs). Background extraction is fire-and-forget by design, so we keep a
# strong reference here for the task's lifetime and drop it once it's done.
_background_tasks: set[asyncio.Task[None]] = set()


def _spawn_background(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _info(row: HubDocument) -> HubDocumentInfo:
    return HubDocumentInfo(
        id=row.id,
        owner_id=row.owner_id,
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        status=row.status,
        parser=row.parser,
        page_count=row.page_count,
        error=row.error,
        summary=row.summary,
        created_at=row.created_at,
    )


async def _read_capped(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="Файл больше 20 МБ")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/documents")
async def upload_document(
    file: UploadFile,
    store: Annotated[DocumentStore, Depends(get_store)],
    blob: Annotated[BlobStore, Depends(get_blob_store)],
    session_factory: Annotated[object, Depends(get_session_factory)],
    x_user_id: Annotated[str, Header()],
) -> HubDocumentInfo:
    owner_id = x_user_id
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=422, detail="Поддерживаются только .docx и .pdf")
    data = await _read_capped(file)
    content_hash = hashlib.sha256(data).hexdigest()

    existing = await store.get_by_hash(owner_id, content_hash)
    if existing is not None:
        return _info(existing)

    filename = file.filename or f"file{suffix}"
    content_type = file.content_type or "application/octet-stream"
    doc_id = str(uuid4())
    s3_key = f"owner/{owner_id}/{doc_id}/original{suffix}"

    # Upload before any DB write: a failed/partial S3 put must never leave a
    # row pointing at bytes that don't exist.
    await blob.put(s3_key, data, content_type)

    try:
        doc = await store.create(
            id=doc_id,
            owner_id=owner_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            content_hash=content_hash,
            s3_key=s3_key,
            parser=suffix.lstrip("."),
        )
        await store.commit()
    except IntegrityError:
        # Concurrent identical upload won the unique (owner_id, content_hash).
        await store.rollback()
        await blob.delete(s3_key)  # best-effort: drop our now-orphan object
        winner = await store.get_by_hash(owner_id, content_hash)
        assert winner is not None
        return _info(winner)

    _spawn_background(
        run_extraction(session_factory, doc.id, data, filename)  # type: ignore[arg-type]
    )
    return _info(doc)


@router.get("/documents")
async def list_documents(
    store: Annotated[DocumentStore, Depends(get_store)],
    x_user_id: Annotated[str, Header()],
) -> HubDocumentListResponse:
    owner_id = x_user_id
    rows = await store.list_for_owner(owner_id)
    return HubDocumentListResponse(documents=[_info(r) for r in rows])


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    x_user_id: Annotated[str, Header()],
) -> HubDocumentInfo:
    row = await store.get_for_owner(x_user_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return _info(row)


@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    x_user_id: Annotated[str, Header()],
) -> HubDocumentContent:
    row = await store.get_for_owner(x_user_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return HubDocumentContent(
        id=row.id,
        status=row.status,
        full_text=row.full_text,
        sections=[HubSection(**s) for s in row.sections],
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    blob: Annotated[BlobStore, Depends(get_blob_store)],
    x_user_id: Annotated[str, Header()],
) -> RedirectResponse:
    row = await store.get_for_owner(x_user_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    if not row.s3_key:
        raise HTTPException(status_code=410, detail="оригинал недоступен")
    url = await blob.presigned_url(row.s3_key, filename=row.filename)
    return RedirectResponse(url=url, status_code=307)


@router.post("/documents/{document_id}/attachments")
async def attach_document(
    document_id: str,
    body: AttachRequest,
    store: Annotated[DocumentStore, Depends(get_store)],
    x_user_id: Annotated[str, Header()],
) -> HubDocumentInfo:
    row = await store.get_for_owner(x_user_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    await store.attach(document_id, body.conversation_id)
    await store.commit()
    return _info(row)


@router.delete("/documents/{document_id}/attachments/{conversation_id}", status_code=204)
async def detach_document(
    document_id: str,
    conversation_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    x_user_id: Annotated[str, Header()],
) -> Response:
    row = await store.get_for_owner(x_user_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    await store.detach(document_id, conversation_id)
    await store.commit()
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/documents")
async def conversation_documents(
    conversation_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    x_user_id: Annotated[str, Header()],
) -> HubDocumentListResponse:
    rows = await store.list_for_conversation(conversation_id, x_user_id)
    return HubDocumentListResponse(documents=[_info(r) for r in rows])


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_store)],
    blob: Annotated[BlobStore, Depends(get_blob_store)],
    x_user_id: Annotated[str, Header()],
) -> Response:
    row = await store.get_for_owner(x_user_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    if row.s3_key:
        await blob.delete(row.s3_key)
    await store.delete(document_id)
    await store.commit()
    return Response(status_code=204)
