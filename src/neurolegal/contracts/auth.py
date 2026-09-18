"""Auth HTTP shapes (agent `/auth/*` + `PATCH /profile`).

`MeResponse` covers `/auth/register`, `/auth/login` and `/auth/me` — since
T-0026 register answers exactly like login (immediate session, no email
verification), so the mail-flow request DTOs are gone. T-0126 extends it
with the profile fields (all optional — the profile is fully skippable)
and adds `ProfileUpdateRequest` for the partial `PATCH /profile`.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# The single password rule (design doc §1.3): minimum 8 characters, no
# composition requirements. Applies on registration (and the operator
# password reset) — never on login, so a future policy change can't lock
# out existing accounts.
PASSWORD_MIN_LENGTH = 8

# Profile field limits (E19 spec §5).
NAME_MAX_LENGTH = 100
AVATAR_PRESET_MAX = 5

UsageKind = Literal["personal", "business"]
ProfileRole = Literal["lawyer", "accountant", "manager", "other"]
# Task keys are identical for both usage kinds — only the labels differ (§4).
ProfileTaskKey = Literal["law_questions", "contract_review", "drafting", "files"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MeResponse(BaseModel):
    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_preset: int | None = None
    usage_kind: UsageKind | None = None
    role: ProfileRole | None = None
    tasks: list[ProfileTaskKey] | None = None
    onboarded_at: datetime | None = None
    # Продуктовый тур (T-0132, спека E19 §9): отметка завершения/пропуска и
    # суммарное число заданных вопросов (user-сообщений по всем беседам) —
    # по нему фронт скрывает пилюлю тура после трёх.
    tour_completed_at: datetime | None = None
    questions_asked: int = 0


class ProfileUpdateRequest(BaseModel):
    """Partial profile update: only the fields present in the request body
    are applied (`exclude_unset` semantics in the route). `onboarded: true`
    and `tour_completed: true` stamp their timestamps once — repeats are
    idempotent."""

    first_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    last_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    avatar_preset: int | None = Field(default=None, ge=0, le=AVATAR_PRESET_MAX)
    usage_kind: UsageKind | None = None
    role: ProfileRole | None = None
    tasks: list[ProfileTaskKey] | None = None
    onboarded: bool = False
    tour_completed: bool = False
