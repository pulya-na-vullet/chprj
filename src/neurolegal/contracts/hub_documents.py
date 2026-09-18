"""Client-facing DTOs for the documents hub (neurolegal-documents-api).

Single source of truth for the hub's HTTP boundary; the service and any HTTP
client both import these.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

HubDocumentStatus = Literal["processing", "ready", "failed"]


class HubSection(BaseModel):
    number: str
    title: str | None = None
    text: str
    level: int
    start: int
    end: int


class HubDocumentInfo(BaseModel):
    id: str
    owner_id: str
    filename: str
    content_type: str
    size: int
    status: HubDocumentStatus
    parser: str
    page_count: int | None = None
    error: str | None = None
    # T-0017: однострочная LLM-выжимка «Суть»; None — не посчитана
    summary: str | None = None
    created_at: datetime


class HubDocumentContent(BaseModel):
    id: str
    status: HubDocumentStatus
    full_text: str
    sections: list[HubSection]


class HubDocumentListResponse(BaseModel):
    documents: list[HubDocumentInfo]


class AttachRequest(BaseModel):
    conversation_id: str


class DownloadResponse(BaseModel):
    url: str


class UploadResponse(BaseModel):
    """Agent upload-proxy response: the hub document plus the conversation it
    was attached to (the frontend needs session_id for newly created chats)."""

    document: HubDocumentInfo
    session_id: str


class AttachLibraryRequest(BaseModel):
    """Attach an existing library document to a conversation; session_id=None
    creates a new conversation (mirrors the upload flow)."""

    session_id: str | None = None
