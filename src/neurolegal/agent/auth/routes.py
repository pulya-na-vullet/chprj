"""`/auth/*` — registration, login/logout, current user.

MVP without email verification (T-0026): register behaves like login — it
answers with `MeResponse` and sets the session cookie, so the SPA drops
straight into the shell. A taken email is an explicit 409 `email_taken`
(the old anti-enumeration 200 is meaningless once success hands back a
session). The mail-based routes (verify-email / resend-verification /
request-password-reset / reset-password) are gone; password reset is an
operator action on the admin "users" surface.
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from neurolegal.agent.auth.deps import (
    SESSION_COOKIE_NAME,
    get_auth_service,
    get_current_user,
    get_rate_limiter,
)
from neurolegal.agent.auth.limiter import RateLimiter
from neurolegal.agent.auth.service import (
    SESSION_TTL,
    AuthService,
    EmailTakenError,
    InvalidCredentialsError,
    LoginResult,
    _aware_utc,
)
from neurolegal.agent.store.models import UserRow
from neurolegal.contracts import (
    LoginRequest,
    MeResponse,
    ProfileRole,
    ProfileTaskKey,
    ProfileUpdateRequest,
    RegisterRequest,
    UsageKind,
)
from neurolegal.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# PATCH /profile живёт вне префикса /auth (спека E19 §5), поэтому отдельный
# роутер; подключается в api/app.py следом за auth_router.
profile_router = APIRouter(tags=["profile"])

_RATE_LIMIT_WINDOW_SECONDS = 300.0
_SESSION_COOKIE_MAX_AGE = int(SESSION_TTL.total_seconds())


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(limiter: RateLimiter, key: str, *, limit: int) -> None:
    if not limiter.allow(key, limit=limit, window_seconds=_RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="rate_limited")


def _me_response(user: UserRow, *, questions_asked: int = 0) -> MeResponse:
    # UserRow хранит usage_kind/role/tasks как строки (SQLite-portable JSON);
    # значения пишутся только через валидированный ProfileUpdateRequest, так
    # что сужение до Literal-типов контракта — безопасный cast.
    return MeResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_preset=user.avatar_preset,
        usage_kind=cast(UsageKind | None, user.usage_kind),
        role=cast(ProfileRole | None, user.role),
        tasks=cast(list[ProfileTaskKey] | None, user.tasks),
        # _aware_utc: SQLite (тесты) отдаёт naive datetime после round-trip,
        # Postgres — aware; нормализуем, чтобы сериализация ISO была стабильной.
        onboarded_at=_aware_utc(user.onboarded_at) if user.onboarded_at is not None else None,
        tour_completed_at=(
            _aware_utc(user.tour_completed_at) if user.tour_completed_at is not None else None
        ),
        questions_asked=questions_asked,
    )


def _set_session_cookie(
    response: Response, result: LoginResult, questions_asked: int
) -> MeResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.session_token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=_SESSION_COOKIE_MAX_AGE,
        secure=settings.cookie_secure,
    )
    return _me_response(result.user, questions_asked=questions_asked)


@router.post("/register", response_model=MeResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> MeResponse:
    _enforce_rate_limit(limiter, f"register:ip:{_client_ip(request)}", limit=5)
    try:
        result = await service.register(payload.email, payload.password)
    except EmailTakenError:
        raise HTTPException(status_code=409, detail="email_taken") from None
    # свежая регистрация — вопросов ещё нет, счёт не запрашиваем
    return _set_session_cookie(response, result, questions_asked=0)


@router.post("/login", response_model=MeResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> MeResponse:
    _enforce_rate_limit(limiter, f"login:ip:{_client_ip(request)}", limit=10)
    _enforce_rate_limit(limiter, f"login:email:{payload.email.strip().lower()}", limit=5)
    try:
        result = await service.login(payload.email, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="invalid_credentials") from None
    return _set_session_cookie(
        response, result, questions_asked=await service.count_user_questions(result.user.id)
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if raw is not None:
        await service.logout(raw)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeResponse)
async def me(
    user: Annotated[UserRow, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    return _me_response(user, questions_asked=await service.count_user_questions(user.id))


@profile_router.patch("/profile", response_model=MeResponse)
async def patch_profile(
    payload: ProfileUpdateRequest,
    user: Annotated[UserRow, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MeResponse:
    # exclude_unset: применяем только реально присланные поля — частичный
    # PATCH не сбрасывает остальной профиль (T-0126).
    changes = payload.model_dump(exclude_unset=True)
    onboarded = bool(changes.pop("onboarded", False))
    tour_completed = bool(changes.pop("tour_completed", False))
    updated = await service.update_profile(
        user.id, changes, onboarded=onboarded, tour_completed=tour_completed
    )
    return _me_response(updated, questions_asked=await service.count_user_questions(user.id))
