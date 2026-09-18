"""Agent-owned conversation tables.

These tables use plain ``String(36)`` UUID PKs (generated in Python) and
generic ``JSON``, so the identical models run on SQLite in unit tests and
on Postgres in production. They are independent of the rag schema.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
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


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # `updated_at` is bumped explicitly by `ConversationStore.append_message`
    # via raw SQL (UPDATE … SET next_ordinal = next_ordinal + 1,
    # updated_at = :now). No ORM-tracked mutation path exists, so we don't
    # set `onupdate=_now` — that would silently overwrite the raw-SQL value
    # if a future caller ever loaded and modified a ConversationRow.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    next_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_conversations_user_id", "user_id"),)


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    web_sources: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    review: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ask: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    # E20: payload'ы карточек шаблонного флоу (TemplateDraftEventData /
    # DocumentReadyEventData) — панель сводки и карточка документа переживают
    # перезагрузку истории тем же приёмом, что review-карточка.
    template_draft: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    template_doc: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("conversation_id", "ordinal", name="uq_messages_conversation_ordinal"),
        Index("ix_messages_conversation_id", "conversation_id"),
    )


class TemplateDraftRow(Base):
    """Staged-черновик заполнения шаблона (E20, спека §6) — один на беседу.

    Инвариант доверия: render_template рендерит ровно эти values — LLM не
    может подменить значения между подтверждением и рендером. Повторный
    stage перезаписывает черновик. ``rendered_at`` — NULL пока документ не
    сформирован; строка без rendered_at также привязывает беседу к
    шаблонному режиму (вход из витрины создаёт запись без значений до
    первого stage).
    ``template_title`` хранится локально, чтобы сводка и имя файла не
    требовали похода в templates-сервис.
    ``document_id`` (T-0143) пишется сразу после upload — до attach: он
    делает render идемпотентным, и оборванную попытку — довершаемой."""

    __tablename__ = "template_drafts"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    template_slug: Mapped[str] = mapped_column(String, nullable=False)
    template_title: Mapped[str] = mapped_column(String, nullable=False)
    values: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    sources: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Stored lower-cased; normalization happens in the auth service, the
    # unique index is the last line of defense.
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    # Профиль-онбординг (T-0126, спека E19 §4): все поля nullable — профиль
    # полностью пропускаемый. Значения usage_kind/role/tasks валидируются
    # контрактом PATCH /profile (contracts/auth.py), БД хранит их как есть.
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_preset: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    usage_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    tasks: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Продуктовый тур (T-0132, спека E19 §9): отметка «тур завершён/пропущен».
    tour_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # sha256 hex of the opaque token; the raw token exists only in the cookie.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (Index("ix_auth_sessions_user_id", "user_id"),)


class AuthTokenRow(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "email_verify" | "password_reset"
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_auth_tokens_user_id", "user_id"),)
