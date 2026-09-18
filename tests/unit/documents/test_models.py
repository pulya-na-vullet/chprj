import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from neurolegal.documents.store.models import (
    Base,
    HubDocument,
    HubDocumentAttachment,
)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_insert_document_and_attachment(session: AsyncSession):
    doc = HubDocument(
        owner_id="default",
        filename="c.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=123,
        content_hash="abc",
        s3_key="owner/default/x/original.docx",
        status="processing",
        parser="docx",
        full_text="",
        sections=[],
    )
    session.add(doc)
    await session.flush()
    assert doc.id  # uuid generated in Python
    att = HubDocumentAttachment(document_id=doc.id, conversation_id="conv-1")
    session.add(att)
    await session.flush()
    assert att.id
