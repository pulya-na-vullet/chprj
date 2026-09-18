from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

EMBEDDING_DIM = 1024

LegalActKind = Literal["codex", "federal_law"]


class LegalAct(BaseModel):
    id: UUID
    kind: LegalActKind
    short_name: str
    full_name: str
    source: str
    source_doc_id: str
    redaction: str | None = None
    ingested_at: datetime


StructureType = Literal["part", "section", "subsection", "chapter", "paragraph"]


class StructureNode(BaseModel):
    id: UUID
    act_id: UUID
    parent_id: UUID | None = None
    type: StructureType
    number: str
    title: str | None = None
    ordinal: int


class ArticlePoint(BaseModel):
    number: str | None = None
    text: str


class Article(BaseModel):
    id: UUID
    act_id: UUID
    parent_node_id: UUID | None = None
    number: str
    title: str | None = None
    full_text: str
    ordinal: int
    points: list[ArticlePoint] | None = None


class Chunk(BaseModel):
    id: UUID
    article_id: UUID
    act_id: UUID
    path: str
    part_number: str | None = None
    point_number: str | None = None
    sub_point_number: str | None = None
    text: str
    ordinal: int
    embedding: Annotated[list[float], Field(min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)]
    structure_path: dict[str, str]

    @field_validator("structure_path")
    @classmethod
    def _has_article(cls, v: dict[str, str]) -> dict[str, str]:
        if "article" not in v:
            raise ValueError("structure_path must contain 'article'")
        return v


class RawDocument(BaseModel):
    source: str
    source_doc_id: str
    fetched_at: datetime
    content_type: str
    body_bytes: bytes


class StructuredDoc(BaseModel):
    act: LegalAct
    structure_nodes: list[StructureNode]
    articles: list[Article]
