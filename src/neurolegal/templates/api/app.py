"""Templates service FastAPI app (neurolegal-templates-api).

ASGI: neurolegal.templates.api.app:app (:8003). Публичная поверхность —
витрина и рендер (за агентом); операторский CRUD — /admin/templates* за
X-Internal-Token (ходит только RAG-прокси, браузер — никогда).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from neurolegal.core.config import settings as core_settings
from neurolegal.core.logging_setup import configure_logging
from neurolegal.templates.api.deps import verify_internal_token
from neurolegal.templates.api.routes_admin import router as admin_router
from neurolegal.templates.api.routes_templates import router as templates_router


def check_internal_token(require_internal_token: bool, internal_token: str | None) -> None:
    """Fail-fast решение T-0139 (спека §9): тот же флаг, что и в сервисе документов.

    Оператор потребовал internal token (NEUROLEGAL_REQUIRE_INTERNAL_TOKEN),
    но не задал значение — /admin/templates* оказались бы открытыми; это
    misconfiguration, на которой честнее упасть на старте. Своя копия
    5-строчной проверки: импортировать хабовскую нельзя (boundary)."""
    if require_internal_token and not internal_token:
        raise RuntimeError(
            "NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true, но NEUROLEGAL_INTERNAL_TOKEN не задан: "
            "операторские /admin/templates* остались бы без аутентификации."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    check_internal_token(core_settings.require_internal_token, core_settings.internal_token)
    yield


app = FastAPI(title="neurolegal-templates-api", version="0.1.0", lifespan=lifespan)
app.include_router(templates_router)
app.include_router(admin_router, dependencies=[Depends(verify_internal_token)])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
