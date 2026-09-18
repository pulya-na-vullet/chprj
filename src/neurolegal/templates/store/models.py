"""Templates-service-owned table.

String(36) UUID PKs (generated in Python) + generic JSON, so the model runs
identically on SQLite (unit tests) and Postgres (production). Independent of
the neurolegal.agent / neurolegal.rag / neurolegal.documents schemas.

User values are never stored here: fill drafts live on the agent's side,
rendered files in the documents hub.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class TplTemplate(Base):
    __tablename__ = "tpl_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    # Список TemplateField (contracts/templates.py) как plain dict'ы.
    fields: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (UniqueConstraint("slug", name="uq_tpl_templates_slug"),)
