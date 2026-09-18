"""Hub-owned document tables.

String(36) UUID PKs (generated in Python) + generic JSON, so the models run
identically on SQLite (unit tests) and Postgres (production). Independent of
the neurolegal.agent and neurolegal.rag schemas.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class HubDocument(Base):
    __tablename__ = "hub_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String, nullable=False, default="default")
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    # NULL for legacy rows migrated without their original bytes (Phase B).
    s3_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    parser: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sections: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # T-0017: однострочная LLM-выжимка «Суть»; NULL — ещё не посчитана
    # (или LLM недоступен). Sweep на старте сервиса досчитывает NULL-строки.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "content_hash", name="uq_hub_documents_owner_hash"),
        Index("ix_hub_documents_owner_id", "owner_id"),
    )


class HubDocumentAttachment(Base):
    __tablename__ = "hub_document_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hub_documents.id", ondelete="CASCADE"), nullable=False
    )
    # Soft reference: conversations live in the agent's tables. No cross-service FK.
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id", "conversation_id", name="uq_hub_attach_document_conversation"
        ),
        Index("ix_hub_attach_document_id", "document_id"),
        Index("ix_hub_attach_conversation_id", "conversation_id"),
    )
