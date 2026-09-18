import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from neurolegal.core.config import settings
from neurolegal.core.logging_setup import configure_logging
from neurolegal.rag.api.routes_acts import router as acts_router
from neurolegal.rag.api.routes_admin_agent import router as admin_agent_router
from neurolegal.rag.api.routes_admin_documents import router as admin_documents_router
from neurolegal.rag.api.routes_admin_jobs import router as admin_jobs_router
from neurolegal.rag.api.routes_admin_templates import router as admin_templates_router
from neurolegal.rag.api.routes_admin_users import router as admin_users_router
from neurolegal.rag.api.routes_article import router as article_router
from neurolegal.rag.api.routes_embed import router as embed_router
from neurolegal.rag.api.routes_health import router as health_router
from neurolegal.rag.api.routes_search import router as search_router
from neurolegal.rag.api.routes_sources import router as sources_router
from neurolegal.rag.jobs import JobManager, make_ingest_runner

_log = logging.getLogger(__name__)


def _warn_admin_open() -> None:
    """Warn that the admin surface is unauthenticated by design.

    /admin/* (and the SPA on /) have no auth and proxy account management —
    user listing and operator password reset — to the agent. Fine on loopback,
    an account-takeover path the moment the RAG service is exposed.
    """
    _log.warning(
        "NEUROLEGAL_ADMIN_ENABLED=True: админ-поверхность (/admin/*) и SPA открыты "
        "без аутентификации и проксируют управление пользователями агента "
        "(перечисление, сброс пароля). Держите RAG-сервис на loopback; перед "
        "любым внешним экспонированием задайте NEUROLEGAL_ADMIN_ENABLED=False."
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    if settings.admin_enabled:
        _warn_admin_open()
        app.state.job_manager = JobManager(
            make_ingest_runner(manifest_path=Path("corpus/manifest.yaml"))
        )
    yield


app = FastAPI(title="Neurolegal RAG", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(embed_router)
app.include_router(search_router)
app.include_router(article_router)
app.include_router(acts_router)
app.include_router(sources_router)
if settings.admin_enabled:
    app.include_router(admin_documents_router)
    app.include_router(admin_jobs_router)
    app.include_router(admin_agent_router)
    app.include_router(admin_users_router)
    app.include_router(admin_templates_router)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Admin SPA (built by `npm run build:admin` into static/). Routes are matched
# before mounts, so /search, /healthz etc. keep working. The dir-exists guard
# lets the backend run before the first frontend build.
_STATIC_DIR = Path(__file__).parent / "static"
if settings.admin_enabled and _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="admin-ui")
