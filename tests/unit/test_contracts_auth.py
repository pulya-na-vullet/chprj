"""Auth DTO validation: email shape and the single password rule (min 8)."""

import pytest
from pydantic import ValidationError

from neurolegal.contracts import LoginRequest, MeResponse, RegisterRequest


def test_register_accepts_valid_input() -> None:
    req = RegisterRequest(email="user@example.com", password="longenough")
    assert req.email == "user@example.com"


def test_register_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="longenough")


def test_register_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="short12")


def test_login_has_no_password_length_rule() -> None:
    # Login must accept whatever the user typed — length policing at login
    # would lock out accounts created before a future policy change.
    req = LoginRequest(email="user@example.com", password="x")
    assert req.password == "x"


def test_mail_flow_dtos_are_gone() -> None:
    """T-0026: the mail-based flows left no dead DTOs behind."""
    import neurolegal.contracts as contracts

    for name in (
        "ResendVerificationRequest",
        "RequestPasswordResetRequest",
        "ResetPasswordRequest",
    ):
        assert not hasattr(contracts, name)


def test_me_response_shape() -> None:
    """Профильные поля (T-0126) опциональны: голый MeResponse валиден,
    профиль по умолчанию пуст."""
    me = MeResponse(id="u1", email="user@example.com")
    assert me.model_dump() == {
        "id": "u1",
        "email": "user@example.com",
        "first_name": None,
        "last_name": None,
        "avatar_preset": None,
        "usage_kind": None,
        "role": None,
        "tasks": None,
        "onboarded_at": None,
        # тур (T-0132): отметка завершения + счётчик заданных вопросов
        "tour_completed_at": None,
        "questions_asked": 0,
    }


def test_profile_update_request_validates_enums_and_lengths() -> None:
    """Валидация PATCH /profile (спека E19 §5) живёт в контракте."""
    from neurolegal.contracts import ProfileUpdateRequest

    ok = ProfileUpdateRequest(
        first_name="Ася",
        avatar_preset=5,
        usage_kind="business",
        role="lawyer",
        tasks=["law_questions", "files"],
        onboarded=True,
    )
    assert ok.tasks == ["law_questions", "files"]

    # частичность: пустое тело валидно, флаги по умолчанию False
    empty = ProfileUpdateRequest()
    assert empty.onboarded is False
    assert empty.tour_completed is False
    assert empty.model_dump(exclude_unset=True) == {}

    for bad in (
        {"usage_kind": "corporate"},
        {"role": "ceo"},
        {"tasks": ["hacking"]},
        {"first_name": "и" * 101},
        {"avatar_preset": 6},
        {"avatar_preset": -1},
    ):
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(**bad)  # type: ignore[arg-type]
