"""Public DTOs for the RAG HTTP surface.

These types are part of the stable contract between RAG, agent, and any web
client. Internal ingestion types (Chunk, Article, RawDocument, StructuredDoc)
stay in `neurolegal.core.domain` — they describe parser/embedder state, not the
HTTP boundary."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from neurolegal.core.domain import EMBEDDING_DIM
from neurolegal.core.domain import LegalActKind as LegalActKind


class SearchedChunk(BaseModel):
    chunk_id: UUID
    path: str
    text: str
    score: float


class SearchedArticle(BaseModel):
    article_id: UUID
    act_short_name: str
    act_kind: LegalActKind
    number: str
    title: str | None = None
    full_text: str
    matched_chunks: list[SearchedChunk]
    score: float


class SearchResponse(BaseModel):
    articles: list[SearchedArticle]


# Single owner of the query-length cap shared by /search, /retrieve and the
# agent's rag_search tool (which clamps LLM-generated queries to fit).
SEARCH_QUERY_MAX_CHARS = 500


class RetrieveRequest(BaseModel):
    query_text: Annotated[str, Field(min_length=1, max_length=SEARCH_QUERY_MAX_CHARS)]
    query_vector: Annotated[list[float], Field(min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)]
    acts: list[str] | None = None
    limit: Annotated[int, Field(ge=1, le=50)] = 8
    # None means "use the configured deployment floor"; an explicit value
    # (including 0.0) overrides settings.rag_min_score for this request.
    min_score: Annotated[float | None, Field(ge=0.0)] = None


EMBED_MAX_TEXT_CHARS = 8000
EMBED_MAX_BATCH_CHARS = 200_000


class EmbedRequest(BaseModel):
    texts: Annotated[list[str], Field(min_length=1, max_length=128)]

    @field_validator("texts")
    @classmethod
    def _bound_text_length(cls, v: list[str]) -> list[str]:
        for i, t in enumerate(v):
            if len(t) > EMBED_MAX_TEXT_CHARS:
                raise ValueError(f"texts[{i}] exceeds EMBED_MAX_TEXT_CHARS={EMBED_MAX_TEXT_CHARS}")
        total = sum(len(t) for t in v)
        if total > EMBED_MAX_BATCH_CHARS:
            raise ValueError(
                f"total text length {total} exceeds EMBED_MAX_BATCH_CHARS={EMBED_MAX_BATCH_CHARS}"
            )
        return v


class EmbedResponse(BaseModel):
    vectors: list[list[float]]


class ActSummary(BaseModel):
    short_name: str
    full_name: str
    kind: str


class ActsResponse(BaseModel):
    acts: list[ActSummary]
