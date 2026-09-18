from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from neurolegal.core.domain import EMBEDDING_DIM


class Base(DeclarativeBase):
    pass


class ActRow(Base):
    __tablename__ = "acts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    short_name: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_doc_id: Mapped[str] = mapped_column(String, nullable=False)
    redaction: Mapped[str | None] = mapped_column(String)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Акт опознаётся по source_doc_id: источник (local-docx / s3-docx /
    # pravo) — описательное поле, при смене акваера строка обновляется
    # вместо задваивания.
    __table_args__ = (UniqueConstraint("source_doc_id", name="uq_acts_source_doc_id"),)


class StructureNodeRow(Base):
    __tablename__ = "structure_nodes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    act_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("acts.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("structure_nodes.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_structure_nodes_act_id", "act_id"),)


class ArticleRow(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    act_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("acts.id", ondelete="CASCADE"), nullable=False
    )
    parent_node_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("structure_nodes.id", ondelete="SET NULL")
    )
    number: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("act_id", "number", name="uq_articles_act_number"),)


class ChunkRow(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    article_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    act_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("acts.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    part_number: Mapped[str | None] = mapped_column(String)
    point_number: Mapped[str | None] = mapped_column(String)
    sub_point_number: Mapped[str | None] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    structure_path: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    # Generated column maintained by Postgres; never written by the application.
    # Declared here so alembic autogen doesn't see it as drift. Migration 0002
    # creates the column without NOT NULL (Postgres' default for generated
    # columns), so the model matches that.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', text)", persisted=True),
    )

    __table_args__ = (
        UniqueConstraint("article_id", "ordinal", name="uq_chunks_article_id_ordinal"),
        Index("ix_chunks_article_id", "article_id"),
        Index("ix_chunks_act_id", "act_id"),
        Index(
            "chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("chunks_search_vector_gin", "search_vector", postgresql_using="gin"),
    )
