"""In-process async extraction worker.

Scheduled after upload (row is already `processing`). Runs the CPU-bound
extraction in a worker thread, then flips the row to `ready`/`failed`. Uses a
fresh session — never the request session, which is closed once the HTTP
response is sent.
"""

import logging
from collections.abc import Callable

import anyio.to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.documents.processing.docx import ExtractionError
from neurolegal.documents.processing.pipeline import ExtractionResult, extract
from neurolegal.documents.processing.summary import summarize, summary_enabled
from neurolegal.documents.store.document_store import DocumentStore

logger = logging.getLogger(__name__)


async def run_extraction(
    session_factory: Callable[[], AsyncSession],
    document_id: str,
    data: bytes,
    filename: str,
    *,
    pdf_parser_factory: Callable[[], object] | None = None,
) -> None:
    async with session_factory() as session:
        store = DocumentStore(session)
        extracted: ExtractionResult | None = None
        try:
            result: ExtractionResult = await anyio.to_thread.run_sync(
                lambda: extract(data, filename, pdf_parser_factory=pdf_parser_factory)
            )
        except ExtractionError as exc:
            await store.mark_failed(document_id, error=str(exc))
        except Exception as exc:  # any unexpected failure must not strand the row in "processing"
            await store.mark_failed(document_id, error=f"Ошибка обработки: {exc}")
        else:
            await store.mark_ready(
                document_id,
                full_text=result.full_text,
                sections=result.sections,
                page_count=result.page_count,
                parser=result.parser,
            )
            extracted = result
        await store.commit()
        # T-0017: «Суть» догоняет уже-ready документ; сбой LLM не трогает
        # ни статус, ни ошибку — колонка остаётся NULL, sweep досчитает.
        if extracted is not None and summary_enabled():
            try:
                line = await summarize(extracted.full_text)
            except Exception:
                logger.warning("summary_failed", extra={"document_id": document_id})
                return
            if line:
                await store.set_summary(document_id, line)
                await store.commit()


async def backfill_missing_summaries(
    session_factory: Callable[[], AsyncSession],
) -> None:
    """Досчитать «Суть» для ready-документов без summary.

    Покрывает рестарт посреди выжимки, длительный сбой LLM и бэкфилл
    библиотеки, загруженной до T-0017. Ошибка одного документа не
    прерывает обход; без API-ключа — no-op."""
    if not summary_enabled():
        return
    async with session_factory() as session:
        store = DocumentStore(session)
        rows = await store.list_ready_without_summary()
        for row in rows:
            try:
                line = await summarize(row.full_text)
            except Exception:
                logger.warning("summary_backfill_failed", extra={"document_id": row.id})
                continue
            if line:
                await store.set_summary(row.id, line)
                await store.commit()
