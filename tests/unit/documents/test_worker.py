import io

import pytest
from docx import Document
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import neurolegal.documents.worker as worker_mod
from neurolegal.documents.store.document_store import DocumentStore
from neurolegal.documents.store.models import Base
from neurolegal.documents.worker import backfill_missing_summaries, run_extraction


def _docx_bytes(paragraphs):
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def summary_off_by_default(monkeypatch):
    """«Суть» выключена, пока тест не включит её явно (T-0103, пункт 1).

    tests/conftest.py заливает .env.local в окружение, поэтому в юнит-прогоне
    `summary_enabled()` отвечает True — и `test_run_extraction_marks_ready`
    уходил на openrouter.ai по-настоящему (зелёным оставался лишь потому, что
    воркер глотает исключение). Сеть теперь перекрыта фикстурой
    tests/unit/conftest.py, но полагаться на аварийный тормоз неправильно:
    тест обязан управлять своей зависимостью сам. Тесты про саму «Суть»
    включают её следующим monkeypatch — он перекрывает этот.
    """
    monkeypatch.setattr(worker_mod, "summary_enabled", lambda: False)


@pytest.fixture
async def engine_and_doc():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        store = DocumentStore(s)
        doc = await store.create(
            owner_id="default",
            filename="c.docx",
            content_type="application/octet-stream",
            size=1,
            content_hash="h",
            s3_key="k",
            parser="docx",
        )
        await store.commit()
        doc_id = doc.id
    yield maker, doc_id
    await engine.dispose()


@pytest.fixture
async def engine_two_ready_docs():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids: list[str] = []
    async with maker() as s:
        store = DocumentStore(s)
        for i, text in enumerate(["первый текст", "второй текст"]):
            doc = await store.create(
                owner_id="default",
                filename=f"{i}.docx",
                content_type="application/octet-stream",
                size=1,
                content_hash=f"h{i}",
                s3_key=f"k{i}",
                parser="docx",
            )
            await store.mark_ready(
                doc.id, full_text=text, sections=[], page_count=None, parser="docx"
            )
            await store.commit()
            ids.append(doc.id)
    yield maker, ids[0], ids[1]
    await engine.dispose()


async def test_run_extraction_marks_ready(engine_and_doc):
    maker, doc_id = engine_and_doc
    await run_extraction(maker, doc_id, _docx_bytes(["1. Предмет", "текст"]), "c.docx")
    async with maker() as s:
        row = await DocumentStore(s).get(doc_id)
    assert row is not None and row.status == "ready"
    assert "Предмет" in row.full_text


async def test_run_extraction_marks_failed_on_bad_bytes(engine_and_doc):
    maker, doc_id = engine_and_doc
    await run_extraction(maker, doc_id, b"not a docx", "c.docx")
    async with maker() as s:
        row = await DocumentStore(s).get(doc_id)
    assert row is not None and row.status == "failed" and row.error


async def test_run_extraction_writes_summary(engine_and_doc, monkeypatch):
    maker, doc_id = engine_and_doc

    async def fake_summarize(text: str) -> str | None:
        return "Поставка; оплата 10 дней"

    monkeypatch.setattr(worker_mod, "summarize", fake_summarize)
    monkeypatch.setattr(worker_mod, "summary_enabled", lambda: True)
    await run_extraction(maker, doc_id, _docx_bytes(["1. Предмет", "текст"]), "c.docx")
    async with maker() as s:
        row = await DocumentStore(s).get(doc_id)
    assert row is not None
    assert row.status == "ready"
    assert row.summary == "Поставка; оплата 10 дней"


async def test_summary_failure_keeps_ready(engine_and_doc, monkeypatch):
    maker, doc_id = engine_and_doc

    async def boom(text: str) -> str | None:
        raise RuntimeError("llm down")

    monkeypatch.setattr(worker_mod, "summarize", boom)
    monkeypatch.setattr(worker_mod, "summary_enabled", lambda: True)
    await run_extraction(maker, doc_id, _docx_bytes(["1. Предмет", "текст"]), "c.docx")
    async with maker() as s:
        row = await DocumentStore(s).get(doc_id)
    assert row is not None
    assert row.status == "ready" and row.summary is None and row.error is None


async def test_summary_skipped_when_disabled(engine_and_doc, monkeypatch):
    maker, doc_id = engine_and_doc
    calls: list[str] = []

    async def fake_summarize(text: str) -> str | None:
        calls.append(text)
        return "должно быть проигнорировано"

    monkeypatch.setattr(worker_mod, "summarize", fake_summarize)
    monkeypatch.setattr(worker_mod, "summary_enabled", lambda: False)
    await run_extraction(maker, doc_id, _docx_bytes(["1. Предмет", "текст"]), "c.docx")
    async with maker() as s:
        row = await DocumentStore(s).get(doc_id)
    assert row is not None
    assert row.status == "ready" and row.summary is None
    assert calls == []


async def test_backfill_missing_summaries(engine_two_ready_docs, monkeypatch):
    maker, doc_id1, doc_id2 = engine_two_ready_docs
    calls: list[str] = []

    async def flaky(text: str) -> str | None:
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError("down")
        return "ок"

    monkeypatch.setattr(worker_mod, "summarize", flaky)
    monkeypatch.setattr(worker_mod, "summary_enabled", lambda: True)
    await backfill_missing_summaries(maker)
    async with maker() as s:
        store = DocumentStore(s)
        row1 = await store.get(doc_id1)
        row2 = await store.get(doc_id2)
    assert row1 is not None and row1.summary is None
    assert row2 is not None and row2.summary == "ок"


async def test_backfill_noop_without_key(engine_two_ready_docs, monkeypatch):
    maker, doc_id1, doc_id2 = engine_two_ready_docs

    async def fail_if_called(text: str) -> str | None:
        raise AssertionError("summarize must not be called when disabled")

    monkeypatch.setattr(worker_mod, "summarize", fail_if_called)
    monkeypatch.setattr(worker_mod, "summary_enabled", lambda: False)
    await backfill_missing_summaries(maker)
    async with maker() as s:
        store = DocumentStore(s)
        row1 = await store.get(doc_id1)
        row2 = await store.get(doc_id2)
    assert row1 is not None and row1.summary is None
    assert row2 is not None and row2.summary is None
