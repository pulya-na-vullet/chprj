"""Repository over the agent conversation tables.

The store flushes but never commits — the caller (ChatAgent) decides commit
boundaries: the user message is committed before streaming starts so it
survives a mid-stream failure; the assistant message is committed after the
stream completes.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.agent.store.models import ConversationRow, MessageRow, TemplateDraftRow


@dataclass
class StoredMessage:
    id: str
    role: str
    content: str
    citations: list[dict[str, object]] | None
    web_sources: list[dict[str, object]] | None
    review: dict[str, object] | None
    stopped: bool
    ask: dict[str, object] | None
    created_at: datetime
    template_draft: dict[str, object] | None = None
    template_doc: dict[str, object] | None = None


@dataclass
class ReviewRunRow:
    """Один risk-review прогон для свода GET /reviews (T-0048): либо
    готовый отчёт (`review`), либо сбойный прогон (`ask` c
    kind="review_failed")."""

    message_id: str
    conversation_id: str
    review: dict[str, object] | None
    ask: dict[str, object] | None
    created_at: datetime


@dataclass
class ConversationSummary:
    id: str
    title: str
    updated_at: datetime
    preview: str | None


def _make_title(content: str | None) -> str:
    if not content:
        return "Новый чат"
    flat = " ".join(content.split())
    return flat[:60] + "…" if len(flat) > 60 else flat


PREVIEW_CHARS = 120
_MD_NOISE_RE = re.compile(r"[#*`>]+")


def _make_preview(content: str | None, has_review: bool, stopped: bool) -> str | None:
    """Однострочный итог последнего ответа для «Реестра задач» (T-0014).

    Обычный ответ схлопывается в одну строку без markdown-символов;
    review-ответ представлен первыми двумя строками сводки («Проверка
    по плейбуку … — Риски: …»); оборванный стопом — префикс «Остановлено».
    None — в беседе ещё нет ответа ассистента."""
    if content is None:
        return None
    if has_review:
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        text = " — ".join(_MD_NOISE_RE.sub("", ln).strip() for ln in lines[:2])
    else:
        text = " ".join(_MD_NOISE_RE.sub("", content).split())
    if len(text) > PREVIEW_CHARS:
        text = text[:PREVIEW_CHARS] + "…"
    if stopped:
        text = f"Остановлено · {text}"
    return text or None


class ConversationStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def create_conversation(self, user_id: str) -> str:
        conv = ConversationRow(user_id=user_id)
        self._session.add(conv)
        await self._session.flush()
        return conv.id

    async def conversation_exists(self, conversation_id: str, user_id: str) -> bool:
        result = await self._session.execute(
            select(ConversationRow.id).where(
                ConversationRow.id == conversation_id, ConversationRow.user_id == user_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def load_history(self, conversation_id: str, user_id: str) -> list[StoredMessage]:
        # Ownership is enforced by joining to conversations rather than
        # trusting the caller to have pre-checked conversation_exists — a
        # wrong-owner id must come back empty, not another user's history.
        result = await self._session.execute(
            select(MessageRow)
            .join(ConversationRow, MessageRow.conversation_id == ConversationRow.id)
            .where(
                MessageRow.conversation_id == conversation_id,
                ConversationRow.user_id == user_id,
            )
            .order_by(MessageRow.ordinal)
        )
        return [
            StoredMessage(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=m.citations,
                web_sources=m.web_sources,
                review=m.review,
                stopped=m.stopped,
                ask=m.ask,
                created_at=m.created_at,
                template_draft=m.template_draft,
                template_doc=m.template_doc,
            )
            for m in result.scalars()
        ]

    async def append_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        citations: list[dict[str, object]] | None = None,
        web_sources: list[dict[str, object]] | None = None,
        review: dict[str, object] | None = None,
        stopped: bool = False,
        ask: dict[str, object] | None = None,
        template_draft: dict[str, object] | None = None,
        template_doc: dict[str, object] | None = None,
    ) -> str:
        # Atomic increment: `UPDATE … SET next_ordinal = next_ordinal + 1
        # WHERE id = :id AND user_id = :user_id RETURNING next_ordinal - 1`.
        # The DB row-locks the conversation row for the duration of the
        # update, so concurrent appends serialise on it and each gets a
        # unique ordinal. The (conversation_id, ordinal) unique constraint is
        # the safety net. The user_id filter makes a wrong-owner append a
        # LookupError, same as a missing conversation — never distinguish
        # "not yours" from "doesn't exist" outward.
        result = await self._session.execute(
            text(
                "UPDATE conversations "
                "SET next_ordinal = next_ordinal + 1, updated_at = :now "
                "WHERE id = :id AND user_id = :user_id "
                "RETURNING next_ordinal - 1"
            ),
            {"id": conversation_id, "user_id": user_id, "now": datetime.now(UTC)},
        )
        row = result.first()
        if row is None:
            raise LookupError(f"conversation not found: {conversation_id}")
        ordinal: int = row[0]

        msg = MessageRow(
            conversation_id=conversation_id,
            ordinal=ordinal,
            role=role,
            content=content,
            citations=citations,
            web_sources=web_sources,
            review=review,
            stopped=stopped,
            ask=ask,
            template_draft=template_draft,
            template_doc=template_doc,
        )
        self._session.add(msg)
        await self._session.flush()
        return msg.id

    async def last_message(self, conversation_id: str, user_id: str) -> MessageRow | None:
        # Same ownership idiom as load_history: join to conversations rather
        # than trusting a pre-check, so a wrong-owner id comes back None
        # rather than another user's message.
        result = await self._session.execute(
            select(MessageRow)
            .join(ConversationRow, MessageRow.conversation_id == ConversationRow.id)
            .where(
                MessageRow.conversation_id == conversation_id,
                ConversationRow.user_id == user_id,
            )
            .order_by(MessageRow.ordinal.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def list_review_runs(self, user_id: str) -> list[ReviewRunRow]:
        """Review-прогоны пользователя, новые первыми (T-0048).

        SQL сужает выборку только до assistant-сообщений владельца: наличие
        отчёта нельзя проверить предикатом `review IS NOT NULL` — JSON-тип
        хранит Python-None как JSON-'null' (см. list_conversations), поэтому
        отбор «отчёт или сбойный прогон» делается в Python. Объём MVP это
        допускает; рост — индекс/материализация (спека E07 §9).
        """
        result = await self._session.execute(
            select(
                MessageRow.id,
                MessageRow.conversation_id,
                MessageRow.review,
                MessageRow.ask,
                MessageRow.created_at,
            )
            .join(ConversationRow, MessageRow.conversation_id == ConversationRow.id)
            .where(ConversationRow.user_id == user_id, MessageRow.role == "assistant")
            .order_by(MessageRow.created_at.desc(), MessageRow.ordinal.desc())
        )
        runs: list[ReviewRunRow] = []
        for row in result:
            is_report = row.review is not None
            is_failed = (row.ask or {}).get("kind") == "review_failed"
            if not is_report and not is_failed:
                continue
            runs.append(
                ReviewRunRow(
                    message_id=row.id,
                    conversation_id=row.conversation_id,
                    review=row.review if is_report else None,
                    ask=row.ask,
                    created_at=row.created_at,
                )
            )
        return runs

    async def get_review_report(self, message_id: str, user_id: str) -> ReviewRunRow | None:
        """Готовый review-отчёт по id сообщения (T-0049, экспорт файла).

        Ownership тем же join-идиомом, что last_message: чужой id → None,
        неотличимо от несуществующего. Наличие отчёта проверяется в Python —
        JSON-тип хранит None как JSON-'null' (см. list_review_runs)."""
        result = await self._session.execute(
            select(
                MessageRow.id,
                MessageRow.conversation_id,
                MessageRow.review,
                MessageRow.ask,
                MessageRow.created_at,
            )
            .join(ConversationRow, MessageRow.conversation_id == ConversationRow.id)
            .where(MessageRow.id == message_id, ConversationRow.user_id == user_id)
        )
        row = result.first()
        if row is None or row.review is None:
            return None
        return ReviewRunRow(
            message_id=row.id,
            conversation_id=row.conversation_id,
            review=row.review,
            ask=row.ask,
            created_at=row.created_at,
        )

    async def list_conversations(self, user_id: str) -> list[ConversationSummary]:
        first_msg = (
            select(MessageRow.content)
            .where(MessageRow.conversation_id == ConversationRow.id)
            .order_by(MessageRow.ordinal)
            .limit(1)
            .scalar_subquery()
        )
        # Последний ответ ассистента (T-0014): тот же idiom скалярного
        # подзапроса, что и first_msg, но role='assistant' и ordinal DESC.
        # ВАЖНО: наличие review нельзя проверять SQL-предикатом IS NOT NULL —
        # тип JSON хранит Python-None как JSON-строку 'null', поэтому review
        # выбирается целиком, сравнение делается в Python.
        last_assistant = (
            select(MessageRow.content)
            .where(
                MessageRow.conversation_id == ConversationRow.id,
                MessageRow.role == "assistant",
            )
            .order_by(MessageRow.ordinal.desc())
            .limit(1)
        )
        last_content = last_assistant.scalar_subquery()
        last_review = last_assistant.with_only_columns(MessageRow.review).scalar_subquery()
        last_stopped = last_assistant.with_only_columns(MessageRow.stopped).scalar_subquery()
        result = await self._session.execute(
            select(
                ConversationRow.id,
                ConversationRow.updated_at,
                first_msg.label("first_content"),
                last_content.label("last_content"),
                last_review.label("last_review"),
                last_stopped.label("last_stopped"),
            )
            .where(ConversationRow.user_id == user_id)
            .order_by(ConversationRow.updated_at.desc())
        )
        return [
            ConversationSummary(
                id=row.id,
                title=_make_title(row.first_content),
                updated_at=row.updated_at,
                preview=_make_preview(
                    row.last_content,
                    row.last_review is not None,
                    bool(row.last_stopped),
                ),
            )
            for row in result
        ]

    # --- staged-черновики шаблонов (E20, спека §6) ---
    # Методы принимают conversation_id, чьё владение проверено выше по
    # стеку (ensure_conversation в ChatAgent) — тот же контракт, что и
    # append_message после ensure_conversation.

    async def get_template_draft(self, conversation_id: str) -> TemplateDraftRow | None:
        return await self._session.get(TemplateDraftRow, conversation_id)

    async def bind_template(self, conversation_id: str, slug: str, title: str) -> None:
        """Вход из витрины: привязка беседы к шаблону до первого stage.

        Существующий черновик другого шаблона перезаписывается пустым;
        повторный вход в тот же шаблон сохраняет уже собранные значения."""
        row = await self.get_template_draft(conversation_id)
        if row is None:
            self._session.add(
                TemplateDraftRow(
                    conversation_id=conversation_id,
                    template_slug=slug,
                    template_title=title,
                    values={},
                    sources={},
                )
            )
        elif row.template_slug != slug:
            row.template_slug = slug
            row.template_title = title
            row.values = {}
            row.sources = {}
            row.rendered_at = None
            row.document_id = None
            row.document_filename = None
            row.updated_at = datetime.now(UTC)
        await self._session.flush()

    async def upsert_template_draft(
        self,
        conversation_id: str,
        *,
        slug: str,
        title: str,
        values: dict[str, object],
        sources: dict[str, object],
    ) -> None:
        """Повторный stage перезаписывает черновик беседы целиком.

        Новые данные — новый цикл: прежний документ забывается, иначе
        следующий render вернул бы файл, собранный по старым значениям."""
        row = await self.get_template_draft(conversation_id)
        if row is None:
            row = TemplateDraftRow(
                conversation_id=conversation_id,
                template_slug=slug,
                template_title=title,
            )
            self._session.add(row)
        row.template_slug = slug
        row.template_title = title
        row.values = values
        row.sources = sources
        row.rendered_at = None
        row.document_id = None
        row.document_filename = None
        row.updated_at = datetime.now(UTC)
        await self._session.flush()

    async def record_template_document(
        self, conversation_id: str, *, document_id: str, filename: str
    ) -> None:
        """Запомнить загруженный документ до привязки к беседе (T-0143).

        Между upload и attach сеть может оборваться; сохранённый id — то,
        что превращает повторный render в довершение прошлой попытки
        вместо второй загрузки того же файла."""
        row = await self.get_template_draft(conversation_id)
        if row is not None:
            row.document_id = document_id
            row.document_filename = filename
            row.updated_at = datetime.now(UTC)
            await self._session.flush()

    async def mark_template_rendered(self, conversation_id: str) -> None:
        row = await self.get_template_draft(conversation_id)
        if row is not None:
            row.rendered_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            await self._session.flush()

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        result = await self._session.execute(
            select(ConversationRow).where(
                ConversationRow.id == conversation_id, ConversationRow.user_id == user_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.execute(
            delete(MessageRow).where(MessageRow.conversation_id == conversation_id)
        )
        await self._session.execute(
            delete(TemplateDraftRow).where(TemplateDraftRow.conversation_id == conversation_id)
        )
        await self._session.delete(row)
        await self._session.flush()
        return True
