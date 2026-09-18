"""Repository over the users / auth_sessions tables.

Same commit discipline as `agent.store.conversation_store.ConversationStore`:
methods flush but never commit — the caller (AuthService) decides commit
boundaries. The `auth_tokens` table (and its `AuthTokenRow` model) stays in
the schema but has no repository methods — the mail-based verify/reset flows
were removed in T-0026; git history has the CRUD if they return.
"""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.agent.store.models import AuthSessionRow, ConversationRow, MessageRow, UserRow

# Единственные колонки users, доступные через update_user_profile, — гард от
# mass-assignment (email/password_hash/is_active меняются только своими путями).
PROFILE_COLUMNS = frozenset(
    {
        "first_name",
        "last_name",
        "avatar_preset",
        "usage_kind",
        "role",
        "tasks",
        "onboarded_at",
        "tour_completed_at",
    }
)


class AuthStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    # -- users ---------------------------------------------------------

    async def create_user(
        self, *, email: str, password_hash: str, email_verified_at: datetime | None = None
    ) -> UserRow:
        row = UserRow(email=email, password_hash=password_hash, email_verified_at=email_verified_at)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_user_by_email(self, email: str) -> UserRow | None:
        result = await self._session.execute(select(UserRow).where(UserRow.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> UserRow | None:
        return await self._session.get(UserRow, user_id)

    async def set_password(self, user_id: str, password_hash: str) -> None:
        row = await self._session.get(UserRow, user_id)
        if row is None:
            return
        row.password_hash = password_hash
        await self._session.flush()

    async def set_active(self, user_id: str, is_active: bool) -> UserRow | None:
        """Flip `is_active`, a pure single-column update. Dropping sessions on
        deactivation is orchestrated by `AuthService.admin_patch_user`, which
        owns the everywhere-logout invariant (T-0033) — don't call this in
        isolation to deactivate a user."""
        row = await self._session.get(UserRow, user_id)
        if row is None:
            return None
        row.is_active = is_active
        await self._session.flush()
        return row

    async def update_user_profile(
        self, user_id: str, changes: Mapping[str, object]
    ) -> UserRow | None:
        """Частичное обновление профильных колонок (T-0126). Ключи вне
        PROFILE_COLUMNS — ошибка программиста (не данных): контракт роута
        не пропускает лишних полей."""
        unknown = set(changes) - PROFILE_COLUMNS
        if unknown:
            raise ValueError(f"non-profile fields in update: {sorted(unknown)}")
        row = await self._session.get(UserRow, user_id)
        if row is None:
            return None
        for key, value in changes.items():
            setattr(row, key, value)
        await self._session.flush()
        return row

    async def count_user_questions(self, user_id: str) -> int:
        """Суммарное число user-сообщений по всем беседам пользователя
        (T-0132): по нему фронт скрывает пилюлю тура после трёх вопросов."""
        result = await self._session.execute(
            select(func.count())
            .select_from(MessageRow)
            .join(ConversationRow, MessageRow.conversation_id == ConversationRow.id)
            .where(ConversationRow.user_id == user_id, MessageRow.role == "user")
        )
        return int(result.scalar_one())

    # -- admin (operator "users" tab, T-0022) ---------------------------

    async def count_conversations(self, user_id: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ConversationRow)
            .where(ConversationRow.user_id == user_id)
        )
        return int(result.scalar_one())

    async def list_users_with_conversation_counts(self) -> list[tuple[UserRow, int]]:
        conv_count = (
            select(func.count())
            .select_from(ConversationRow)
            .where(ConversationRow.user_id == UserRow.id)
            .correlate(UserRow)
            .scalar_subquery()
        )
        result = await self._session.execute(
            select(UserRow, conv_count).order_by(UserRow.created_at.desc())
        )
        return [(row[0], row[1]) for row in result]

    # -- sessions --------------------------------------------------------

    async def create_session(
        self, *, user_id: str, token_hash: str, expires_at: datetime
    ) -> AuthSessionRow:
        row = AuthSessionRow(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_session_by_hash(self, token_hash: str) -> AuthSessionRow | None:
        result = await self._session.execute(
            select(AuthSessionRow).where(AuthSessionRow.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def touch_session(
        self, session_id: str, *, last_seen_at: datetime, expires_at: datetime
    ) -> None:
        row = await self._session.get(AuthSessionRow, session_id)
        if row is None:
            return
        row.last_seen_at = last_seen_at
        row.expires_at = expires_at
        await self._session.flush()

    async def delete_session_by_hash(self, token_hash: str) -> bool:
        row = await self.get_session_by_hash(token_hash)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def delete_sessions_for_user(self, user_id: str) -> None:
        await self._session.execute(delete(AuthSessionRow).where(AuthSessionRow.user_id == user_id))
        await self._session.flush()
