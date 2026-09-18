"""Client-facing DTOs for the «Источники права» screen.

Read-only catalog + article drill-down. Served always-on under /sources on
the RAG app and proxied by the agent. Client-safe: no file paths, mtime, db
size, chunk internals, or job state — and status is binary (in_corpus/planned),
never the internal stale/orphaned admin statuses.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SourceSummary(BaseModel):
    source_doc_id: str
    short_name: str
    full_name: str
    kind: str  # "codex" | "federal_law"
    branch: str | None
    redaction: str | None
    status: Literal["in_corpus", "planned"]


class SourcesResponse(BaseModel):
    sources: list[SourceSummary]


class SourceArticleListItem(BaseModel):
    article_id: UUID
    number: str
    title: str | None = None


class SourceArticlesResponse(BaseModel):
    source_doc_id: str
    short_name: str
    articles: list[SourceArticleListItem]


class SourceArticleDetail(BaseModel):
    article_id: UUID
    act_short_name: str
    number: str
    title: str | None = None
    full_text: str
