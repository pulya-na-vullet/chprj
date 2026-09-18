"""Auth business logic: registration, login/session, logout.

MVP without email verification (T-0026, client decision 2026-07-11):
registration is just email + password — the user comes out active and
verified (`email_verified_at = now`) with a session already open, and login
never checks verification. The mail-based flows (verify / resend /
password reset) are gone from the service; password reset is an operator
action on the admin "users" surface. `core/mail` stays in the codebase for
when mail returns.

A duplicate email answers with an explicit `EmailTakenError` — the old
anti-enumeration posture is meaningless once registration must hand back a
live session on success.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.models import UserRow
from neurolegal.core.security import generate_token, hash_password, hash_token, verify_password

SESSION_TTL = timedelta(days=30)
# Sliding-expiry write is throttled to at most once/day per session so a
# chatty user doesn't turn every request into a session UPDATE.
SESSION_REFRESH_THRESHOLD = timedelta(days=1)

# I1: login must not let response latency reveal whether an email is
# registered. verify_password runs against this fixed argon2 hash on the
# "email doesn't exist" branch so it costs the same as the real-credential
# path. Hashed once at import, not per-request.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-parity-only")


def _aware_utc(dt: datetime) -> datetime:
    """Normalize a DB-read datetime to UTC-aware.

    Every value this service writes is `datetime.now(UTC)`-based, but SQLite
    (used in unit tests) round-trips `DateTime(timezone=True)` as naive once
    the ORM re-reads it from a fresh session; Postgres (production) returns
    it aware already. Treat a naive value as UTC rather than local time.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class InvalidCredentialsError(Exception):
    """Unknown email, wrong password, or a deactivated account."""


class EmailTakenError(Exception):
    """Registration against an email that already has an account."""


class UserNotFoundError(Exception):
    """Operator admin action targeting an unknown user id."""


@dataclass
class LoginResult:
    user: UserRow
    session_token: str


class AuthService:
    def __init__(self, *, store: AuthStore) -> None:
        self._store = store

    async def register(self, email: str, password: str) -> LoginResult:
        email = _normalize_email(email)
        existing = await self._store.get_user_by_email(email)
        if existing is not None:
            raise EmailTakenError()
        now = datetime.now(UTC)
        # check-then-act above is not atomic: two concurrent registrations of
        # the same email (double-click, proxy retry) can both pass the check
        # and race on the uq_users_email unique index. Turn that IntegrityError
        # into the same 409 the sequential duplicate gets, mirroring the
        # documents hub's (owner_id, content_hash) race handling.
        try:
            user = await self._store.create_user(
                email=email, password_hash=hash_password(password), email_verified_at=now
            )
        except IntegrityError as exc:
            await self._store.rollback()
            raise EmailTakenError() from exc
        raw = await self._open_session(user.id, now)
        await self._store.commit()
        return LoginResult(user=user, session_token=raw)

    async def login(self, email: str, password: str) -> LoginResult:
        email = _normalize_email(email)
        user = await self._store.get_user_by_email(email)
        # Always call verify_password — against the real hash when the user
        # exists, against a fixed dummy hash otherwise — so a nonexistent
        # email pays the same argon2 cost as a wrong password (I1: a
        # short-circuit here is a response-timing enumeration oracle).
        hashed = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(password, hashed)
        if user is None or not user.is_active or not password_ok:
            raise InvalidCredentialsError()
        raw = await self._open_session(user.id, datetime.now(UTC))
        await self._store.commit()
        return LoginResult(user=user, session_token=raw)

    async def admin_patch_user(
        self,
        user_id: str,
        *,
        is_active: bool | None = None,
        new_password: str | None = None,
    ) -> UserRow:
        """Operator user mutation with the everywhere-logout invariant baked in.

        Deactivation and any password change must immediately invalidate every
        open session for the user. That invariant lived in the route before
        T-0033; keeping it here means every caller — the internal PATCH route
        today, an operator CLI tomorrow — gets it for free rather than having
        to remember to drop sessions after the mutation. Raises
        UserNotFoundError for an unknown id; the caller maps it to 404.
        """
        user = await self._store.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if is_active is not None:
            await self._store.set_active(user_id, is_active)
            if not is_active:
                await self._store.delete_sessions_for_user(user_id)
        if new_password is not None:
            await self._store.set_password(user_id, hash_password(new_password))
            await self._store.delete_sessions_for_user(user_id)
        await self._store.commit()
        return user

    async def update_profile(
        self,
        user_id: str,
        changes: Mapping[str, object],
        *,
        onboarded: bool = False,
        tour_completed: bool = False,
    ) -> UserRow:
        """Частичное обновление профиля (T-0126, спека E19 §5; тур — T-0132).

        `changes` — только реально присланные поля (`exclude_unset` в роуте),
        поэтому частичный PATCH не сбрасывает остальное. Флаги `onboarded` и
        `tour_completed` ставят свои отметки один раз (идемпотентно) и друг
        от друга не зависят: онбординг и тур завершаются в разные моменты.
        """
        user = await self._store.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        applied = dict(changes)
        now = datetime.now(UTC)
        if onboarded and user.onboarded_at is None:
            applied["onboarded_at"] = now
        if tour_completed and user.tour_completed_at is None:
            applied["tour_completed_at"] = now
        if applied:
            updated = await self._store.update_user_profile(user_id, applied)
            if updated is None:
                raise UserNotFoundError()
            user = updated
        await self._store.commit()
        return user

    async def count_user_questions(self, user_id: str) -> int:
        return await self._store.count_user_questions(user_id)

    async def logout(self, raw_token: str) -> None:
        await self._store.delete_session_by_hash(hash_token(raw_token))
        await self._store.commit()

    async def get_current_user(self, raw_token: str) -> UserRow | None:
        now = datetime.now(UTC)
        session = await self._store.get_session_by_hash(hash_token(raw_token))
        if session is None or _aware_utc(session.expires_at) < now:
            return None
        user = await self._store.get_user_by_id(session.user_id)
        if user is None or not user.is_active:
            return None
        if now - _aware_utc(session.last_seen_at) >= SESSION_REFRESH_THRESHOLD:
            await self._store.touch_session(
                session.id, last_seen_at=now, expires_at=now + SESSION_TTL
            )
            await self._store.commit()
        return user

    async def _open_session(self, user_id: str, now: datetime) -> str:
        raw = generate_token()
        await self._store.create_session(
            user_id=user_id, token_hash=hash_token(raw), expires_at=now + SESSION_TTL
        )
        return raw


def _normalize_email(email: str) -> str:
    return email.strip().lower()
