"""Auth tables: users / auth_sessions / auth_tokens (agent-owned, SQLite-portable)."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from neurolegal.agent.store.models import AuthSessionRow, AuthTokenRow, Base, UserRow


def test_table_names() -> None:
    assert UserRow.__tablename__ == "users"
    assert AuthSessionRow.__tablename__ == "auth_sessions"
    assert AuthTokenRow.__tablename__ == "auth_tokens"


def test_user_columns() -> None:
    cols = {c.name for c in UserRow.__table__.columns}
    assert cols == {
        "id",
        "email",
        "password_hash",
        "is_active",
        "email_verified_at",
        "created_at",
        # профиль-онбординг (T-0126) — все nullable
        "first_name",
        "last_name",
        "avatar_preset",
        "usage_kind",
        "role",
        "tasks",
        "onboarded_at",
        # тур по продукту (T-0132) — nullable отметка завершения/пропуска
        "tour_completed_at",
    }


def test_session_columns() -> None:
    cols = {c.name for c in AuthSessionRow.__table__.columns}
    assert cols == {"id", "token_hash", "user_id", "created_at", "expires_at", "last_seen_at"}


def test_token_columns() -> None:
    cols = {c.name for c in AuthTokenRow.__table__.columns}
    assert cols == {"id", "user_id", "purpose", "token_hash", "expires_at", "used_at"}


def test_models_share_agent_metadata() -> None:
    for row in (UserRow, AuthSessionRow, AuthTokenRow):
        assert row.metadata is Base.metadata


def test_client_side_uuid_defaults() -> None:
    for table in (UserRow.__table__, AuthSessionRow.__table__, AuthTokenRow.__table__):
        assert table.c.id.default is not None
        assert table.c.id.default.is_callable
        assert table.c.id.server_default is None


@pytest.fixture()
def engine() -> Engine:
    eng = create_engine("sqlite://")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return eng


def test_email_is_unique(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(UserRow(email="a@b.ru", password_hash="h"))
        db.commit()
        db.add(UserRow(email="a@b.ru", password_hash="h2"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_session_token_hash_is_unique(engine: Engine) -> None:
    from datetime import UTC, datetime

    expires = datetime(2027, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        user = UserRow(email="a@b.ru", password_hash="h")
        db.add(user)
        db.flush()
        db.add(AuthSessionRow(token_hash="t1", user_id=user.id, expires_at=expires))
        db.commit()
        db.add(AuthSessionRow(token_hash="t1", user_id=user.id, expires_at=expires))
        with pytest.raises(IntegrityError):
            db.commit()


def test_deleting_user_cascades_sessions_and_tokens(engine: Engine) -> None:
    from datetime import UTC, datetime

    expires = datetime(2027, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        user = UserRow(email="a@b.ru", password_hash="h")
        db.add(user)
        db.flush()
        db.add(AuthSessionRow(token_hash="t1", user_id=user.id, expires_at=expires))
        db.add(
            AuthTokenRow(
                user_id=user.id, purpose="email_verify", token_hash="v1", expires_at=expires
            )
        )
        db.commit()
        db.delete(user)
        db.commit()
        assert db.query(AuthSessionRow).count() == 0
        assert db.query(AuthTokenRow).count() == 0


def test_new_user_defaults(engine: Engine) -> None:
    with Session(engine) as db:
        user = UserRow(email="a@b.ru", password_hash="h")
        db.add(user)
        db.commit()
        db.refresh(user)
        assert user.is_active is True
        assert user.email_verified_at is None
        assert user.created_at is not None


def test_new_user_profile_defaults_to_empty(engine: Engine) -> None:
    """Профильные колонки (T-0126) — nullable без дефолтов: свежий пользователь
    ничего не заполнял, онбординг не проходил."""
    with Session(engine) as db:
        user = UserRow(email="p@b.ru", password_hash="h")
        db.add(user)
        db.commit()
        db.refresh(user)
        assert user.first_name is None
        assert user.last_name is None
        assert user.avatar_preset is None
        assert user.usage_kind is None
        assert user.role is None
        assert user.tasks is None
        assert user.onboarded_at is None
