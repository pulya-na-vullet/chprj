"""Agent FastAPI app.

Exposes /healthz and the SSE /chat endpoint. Lifespan configures logging the
same way ``neurolegal.rag.api.app`` does. The static SPA lives under ``static/``
and is served on ``/`` by ``StaticFiles``.
"""

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from neurolegal.agent.api.routes_acts import router as acts_router
from neurolegal.agent.api.routes_admin_users import router as admin_users_router
from neurolegal.agent.api.routes_chat import router as chat_router
from neurolegal.agent.api.routes_conversations import router as conversations_router
from neurolegal.agent.api.routes_documents import router as documents_router
from neurolegal.agent.api.routes_reviews import router as reviews_router
from neurolegal.agent.api.routes_sources import router as sources_router
from neurolegal.agent.api.routes_templates import router as templates_router
from neurolegal.agent.auth.routes import profile_router
from neurolegal.agent.auth.routes import router as auth_router
from neurolegal.contracts import (
    AskEventData,
    CitationsEventData,
    DeltaEventData,
    DoneEventData,
    ErrorEventData,
    ReasoningEventData,
    ResetDeltaEventData,
    ReviewProgressEventData,
    SessionEventData,
    ToolCallEventData,
    ToolResultEventData,
    WebSourcesEventData,
)
from neurolegal.core.config import settings
from neurolegal.core.logging_setup import configure_logging

_log = logging.getLogger(__name__)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1"})
_VITE_DEV_ORIGINS = frozenset({"http://localhost:5173", "http://127.0.0.1:5173"})


def _build_allowed_origins(public_base_url: str) -> frozenset[str]:
    """Origin allowlist for the CSRF check below.

    Always includes the browser-facing origin (`public_base_url`); when that
    points at localhost/127.0.0.1 (local dev), also allows the Vite dev
    server's origin, since in dev the SPA is served from :5173 and proxies
    API calls to the agent — same-origin from the browser's point of view,
    but a distinct Origin header on the actual request.
    """
    parsed = urlsplit(public_base_url)
    allowed = {f"{parsed.scheme}://{parsed.netloc}"}
    if parsed.hostname in _LOCAL_HOSTNAMES:
        allowed |= _VITE_DEV_ORIGINS
    return frozenset(allowed)


_ALLOWED_ORIGINS = _build_allowed_origins(settings.public_base_url)


def _check_admin_users_gate() -> None:
    """Guard the internal `/admin/users*` router on this public service.

    The agent is browser-facing (NEUROLEGAL_PUBLIC_BASE_URL), and these routes can
    reset any user's password / deactivate any account. Their only gate is
    `verify_internal_token`, which is a no-op when NEUROLEGAL_INTERNAL_TOKEN is
    unset — fine for a loopback dev box, an account-takeover hole the moment
    the agent is exposed. So: fail fast if the operator opted into requiring
    the token (NEUROLEGAL_REQUIRE_INTERNAL_TOKEN) but never set it, and always
    warn loudly when the routes are mounted open.
    """
    if settings.internal_token:
        return
    if settings.require_internal_token:
        raise RuntimeError(
            "NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true, но NEUROLEGAL_INTERNAL_TOKEN не задан. "
            "Внутренние ручки /admin/users* агента остались бы без аутентификации. "
            "Задайте общий секрет агента и RAG-сервиса перед запуском."
        )
    _log.warning(
        "NEUROLEGAL_INTERNAL_TOKEN не задан: внутренние ручки /admin/users* агента "
        "открыты без аутентификации (перечисление пользователей, сброс пароля). "
        "Это допустимо только для localhost-разработки. Перед любым внешним "
        "экспонированием агента задайте NEUROLEGAL_INTERNAL_TOKEN и "
        "NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true."
    )


def _warn_if_multiworker() -> None:
    """Warn when the agent looks multi-worker.

    The login/register rate limiter (`auth/limiter.py`) and the per-conversation
    turn lock are in-process `dict`s — with >1 uvicorn worker the rate budget is
    multiplied per worker and the turn lock stops being global. There's no
    shared-store yet; until there is, a multi-worker deploy is a known gap, not
    a supported config. `WEB_CONCURRENCY` is the conventional worker-count env.
    """
    raw = os.environ.get("WEB_CONCURRENCY")
    try:
        workers = int(raw) if raw else 1
    except ValueError:
        workers = 1
    if workers > 1:
        _log.warning(
            "WEB_CONCURRENCY=%s: rate limiter и turn-lock агента живут в памяти "
            "процесса — при нескольких воркерах лимиты делятся на воркеры, а "
            "turn-lock перестаёт быть глобальным. Пока нет общего стора это "
            "неподдерживаемая конфигурация (см. T-0032).",
            raw,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    _check_admin_users_gate()
    _warn_if_multiworker()
    yield


app = FastAPI(title="Neurolegal Agent", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def check_origin(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Reject cross-site mutating requests whose Origin isn't ours.

    SameSite=Lax on the session cookie already blocks cross-site POSTs from
    following a link/form, but this is a second, explicit gate. An absent
    Origin (curl, same-origin GET, most simple navigations) passes through —
    browsers reliably send Origin on cross-site fetch/XHR/form POSTs, which
    is exactly what we need to catch.
    """
    if request.method in _MUTATING_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in _ALLOWED_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "invalid_origin"})
    return await call_next(request)


app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(chat_router)
app.include_router(acts_router)
app.include_router(conversations_router)
app.include_router(documents_router)
app.include_router(sources_router)
app.include_router(templates_router)
app.include_router(reviews_router)
app.include_router(admin_users_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# SSE event payloads are not tied to a JSON HTTP operation, so FastAPI would
# otherwise omit them from the OpenAPI schema. Surface them on a hidden
# endpoint so `openapi-typescript` can pick them up.
_SSE_EVENTS = (
    SessionEventData
    | ReasoningEventData
    | ToolCallEventData
    | ToolResultEventData
    | DeltaEventData
    | ResetDeltaEventData
    | CitationsEventData
    | WebSourcesEventData
    | ReviewProgressEventData
    | AskEventData
    | DoneEventData
    | ErrorEventData
)


@app.get("/_internal/sse-schemas", response_model=_SSE_EVENTS, include_in_schema=True)
def _sse_schemas() -> dict[str, object]:  # pragma: no cover - schema-only
    # This endpoint exists purely so the SSE event-payload models appear in
    # the OpenAPI schema (no other operation references them). The returned
    # body is meaningless — what matters is the response_model union above.
    return {}


_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="ui")
