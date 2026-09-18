"""Admin-surface DTOs: corpus documents, ingest jobs, inspection.

Part of the RAG HTTP contract (served under /admin/* on the RAG app).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from neurolegal.core.domain import LegalActKind

DocumentStatus = Literal["not_ingested", "ingested", "stale", "ingesting", "orphaned"]
JobState = Literal["running", "succeeded", "failed", "cancelled"]
JobStage = Literal[
    "starting", "acquiring", "parsing", "chunking", "embedding", "persisting", "indexing"
]

UPLOAD_MAX_BYTES = 20 * 1024 * 1024


class AdminDocument(BaseModel):
    # None for orphaned rows (present in DB, absent from manifest).
    code_id: str | None
    source_doc_id: str
    short_name: str
    full_name: str
    kind: LegalActKind
    status: DocumentStatus
    file_path: str | None = None
    file_exists: bool = False
    file_size: int | None = None
    file_mtime: datetime | None = None
    articles_count: int | None = None
    chunks_count: int | None = None
    ingested_at: datetime | None = None


class AdminDocumentsResponse(BaseModel):
    documents: list[AdminDocument]
    total_chunks: int
    db_size_bytes: int


class ManifestUpdateRequest(BaseModel):
    short_name: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    kind: LegalActKind
    docx_path: str = Field(min_length=1)


class DeleteDocumentRequest(BaseModel):
    drop_manifest: bool = False
    drop_file: bool = False


class UploadDocumentResponse(BaseModel):
    code_id: str
    job_id: str | None = None


class IngestRequest(BaseModel):
    code_id: str = Field(min_length=1)


class IngestAccepted(BaseModel):
    job_id: str


class JobOut(BaseModel):
    id: str
    code_id: str
    state: JobState
    stage: JobStage
    progress_done: int
    progress_total: int
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    articles_count: int | None = None
    chunks_count: int | None = None


class JobsResponse(BaseModel):
    jobs: list[JobOut]


class AdminArticleListItem(BaseModel):
    article_id: UUID
    number: str
    title: str | None = None
    chunks_count: int


class AdminArticlesResponse(BaseModel):
    articles: list[AdminArticleListItem]


class AdminChunkOut(BaseModel):
    chunk_id: UUID
    path: str
    text: str
    ordinal: int


class AdminArticleDetail(BaseModel):
    article_id: UUID
    act_short_name: str
    number: str
    title: str | None = None
    full_text: str
    chunks: list[AdminChunkOut]


class IndexesStatusResponse(BaseModel):
    hnsw: bool
    gin: bool


class OkResponse(BaseModel):
    status: Literal["ok"] = "ok"
