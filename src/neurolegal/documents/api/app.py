"""Documents hub FastAPI app (neurolegal-documents-api).

ASGI: neurolegal.documents.api.app:app. Startup preflights OCR data and
resets any rows stuck in `processing` from a previous crash.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from neurolegal.core.config import settings as core_settings
from neurolegal.core.db import get_sessionmaker
from neurolegal.core.logging_setup import configure_logging
from neurolegal.documents.api.deps import verify_internal_token
from neurolegal.documents.api.routes_documents import router as documents_router
from neurolegal.documents.config import settings
from neurolegal.documents.processing.preflight import check_internal_token, check_tessdata
from neurolegal.documents.store.document_store import DocumentStore
from neurolegal.documents.worker import backfill_missing_summaries


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    check_tessdata(settings.tessdata_path)
    check_internal_token(core_settings.require_internal_token, core_settings.internal_token)
    maker = get_sessionmaker()
    async with maker() as session:
        store = DocumentStore(session)
        await store.reset_stuck_processing()
        await store.commit()
    # T-0017: sweep «Сути» — фоном, старт сервиса не блокирует.
    backfill_task = asyncio.create_task(backfill_missing_summaries(maker))
    yield
    backfill_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await backfill_task


app = FastAPI(title="neurolegal-documents-api", version="0.1.0", lifespan=lifespan)
app.include_router(documents_router, dependencies=[Depends(verify_internal_token)])


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
