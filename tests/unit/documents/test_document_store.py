import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.documents.store.document_store import DocumentStore
from neurolegal.documents.store.models import Base


@pytest.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield DocumentStore(s)
    await engine.dispose()


async def _new(store: DocumentStore, *, hash_="h1"):
    doc = await store.create(
        owner_id="default",
        filename="c.docx",
        content_type="application/octet-stream",
        size=10,
        content_hash=hash_,
        s3_key="owner/default/x/original.docx",
        parser="docx",
    )
    await store.commit()
    return doc


async def test_create_and_get(store: DocumentStore):
    doc = await _new(store)
    assert doc.status == "processing"
    again = await store.get(doc.id)
    assert again is not None and again.filename == "c.docx"


async def test_dedup_by_hash(store: DocumentStore):
    doc = await _new(store)
    dup = await store.get_by_hash("default", "h1")
    assert dup is not None and dup.id == doc.id
    assert await store.get_by_hash("default", "nope") is None


async def test_dedup_by_hash_is_scoped_to_owner(store: DocumentStore):
    """Дедуп по хешу обязан быть внутри владельца (T-0101, пункт 3).

    Без owner_id в WHERE загрузка тех же байтов отдаёт HubDocumentInfo
    ЧУЖОГО документа — id, owner_id, имя файла и «Суть» утекают тому, кто
    просто угадал содержимое (routes_documents.upload_document возвращает
    найденную строку как свою).
    """
    mine = await _new(store)  # owner_id="default", content_hash="h1"
    theirs = await store.create(
        owner_id="attacker",
        filename="their-nda.docx",
        content_type="application/octet-stream",
        size=10,
        content_hash="h1",  # те же байты под другим владельцем — уникальность (owner, hash)
        s3_key="owner/attacker/x/original.docx",
        parser="docx",
    )
    await store.commit()

    found_mine = await store.get_by_hash("default", "h1")
    assert found_mine is not None and found_mine.id == mine.id
    found_theirs = await store.get_by_hash("attacker", "h1")
    assert found_theirs is not None and found_theirs.id == theirs.id
    assert await store.get_by_hash("stranger", "h1") is None


async def test_mark_ready_and_failed(store: DocumentStore):
    doc = await _new(store)
    await store.mark_ready(
        doc.id, full_text="text", sections=[{"number": "1"}], page_count=2, parser="docx"
    )
    await store.commit()
    r = await store.get(doc.id)
    assert r is not None and r.status == "ready" and r.page_count == 2

    doc2 = await _new(store, hash_="h2")
    await store.mark_failed(doc2.id, error="boom")
    await store.commit()
    f = await store.get(doc2.id)
    assert f is not None and f.status == "failed" and f.error == "boom"


async def test_reset_stuck_processing(store: DocumentStore):
    await _new(store)
    n = await store.reset_stuck_processing()
    await store.commit()
    assert n == 1


async def test_attach_is_idempotent_and_lists(store: DocumentStore):
    doc = await _new(store)
    await store.attach(doc.id, "conv-1")
    await store.attach(doc.id, "conv-1")  # no duplicate
    await store.commit()
    docs = await store.list_for_conversation("conv-1", "default")
    assert [d.id for d in docs] == [doc.id]
    await store.detach(doc.id, "conv-1")
    await store.commit()
    assert await store.list_for_conversation("conv-1", "default") == []


async def test_delete(store: DocumentStore):
    doc = await _new(store)
    await store.delete(doc.id)
    await store.commit()
    assert await store.get(doc.id) is None


async def test_get_for_owner_scopes_by_owner(store: DocumentStore):
    doc = await _new(store)  # owner_id="default"
    assert await store.get_for_owner("default", doc.id) is not None
    assert await store.get_for_owner("someone-else", doc.id) is None
    assert await store.get_for_owner("default", "no-such-id") is None


async def test_list_for_conversation_excludes_other_owner(store: DocumentStore):
    mine = await _new(store, hash_="mine")
    theirs = await store.create(
        owner_id="attacker",
        filename="c.docx",
        content_type="application/octet-stream",
        size=10,
        content_hash="theirs",
        s3_key="owner/attacker/x/original.docx",
        parser="docx",
    )
    await store.commit()
    await store.attach(mine.id, "conv-1")
    await store.attach(theirs.id, "conv-1")
    await store.commit()

    docs = await store.list_for_conversation("conv-1", "default")
    assert [d.id for d in docs] == [mine.id]


async def test_set_summary_roundtrip(store: DocumentStore) -> None:
    doc = await store.create(
        owner_id="u1",
        filename="a.docx",
        content_type="x",
        size=1,
        content_hash="h1",
        s3_key="k",
        parser="docx",
    )
    await store.mark_ready(doc.id, full_text="текст", sections=[], page_count=None, parser="docx")
    await store.set_summary(doc.id, "Поставка; оплата 10 дней")
    await store.commit()
    row = await store.get(doc.id)
    assert row is not None and row.summary == "Поставка; оплата 10 дней"


async def test_list_ready_without_summary(store: DocumentStore) -> None:
    a = await store.create(
        owner_id="u1",
        filename="a.docx",
        content_type="x",
        size=1,
        content_hash="ha",
        s3_key="k",
        parser="docx",
    )
    b = await store.create(
        owner_id="u1",
        filename="b.docx",
        content_type="x",
        size=1,
        content_hash="hb",
        s3_key="k",
        parser="docx",
    )
    await store.mark_ready(a.id, full_text="т", sections=[], page_count=None, parser="docx")
    await store.mark_ready(b.id, full_text="т", sections=[], page_count=None, parser="docx")
    await store.set_summary(b.id, "есть")
    await store.commit()
    rows = await store.list_ready_without_summary()
    assert [r.id for r in rows] == [a.id]
