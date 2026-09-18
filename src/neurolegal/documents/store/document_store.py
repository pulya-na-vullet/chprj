"""Repository over hub_documents / hub_document_attachments (flush-not-commit)."""

from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.documents.store.models import HubDocument, HubDocumentAttachment


def _now() -> datetime:
    return datetime.now(UTC)


class DocumentStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def create(
        self,
        *,
        owner_id: str,
        filename: str,
        content_type: str,
        size: int,
        content_hash: str,
        s3_key: str,
        parser: str,
        id: str | None = None,
    ) -> HubDocument:
        row = HubDocument(
            owner_id=owner_id,
            filename=filename,
            content_type=content_type,
            size=size,
            content_hash=content_hash,
            s3_key=s3_key,
            status="processing",
            parser=parser,
            full_text="",
            sections=[],
        )
        if id is not None:
            row.id = id
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, document_id: str) -> HubDocument | None:
        return await self._session.get(HubDocument, document_id)

    async def get_for_owner(self, owner_id: str, document_id: str) -> HubDocument | None:
        """Object-level authorization for the per-document routes: a document
        that exists but belongs to a different owner must read exactly like
        one that doesn't exist (404, never a distinct error)."""
        result = await self._session.execute(
            select(HubDocument).where(
                HubDocument.id == document_id,
                HubDocument.owner_id == owner_id,
            )
        )
        return result.scalars().first()

    async def get_by_hash(self, owner_id: str, content_hash: str) -> HubDocument | None:
        result = await self._session.execute(
            select(HubDocument).where(
                HubDocument.owner_id == owner_id,
                HubDocument.content_hash == content_hash,
            )
        )
        return result.scalars().first()

    async def list_for_owner(self, owner_id: str) -> list[HubDocument]:
        result = await self._session.execute(
            select(HubDocument)
            .where(HubDocument.owner_id == owner_id)
            .order_by(HubDocument.created_at.desc())
        )
        return list(result.scalars())

    async def mark_ready(
        self,
        document_id: str,
        *,
        full_text: str,
        sections: list[dict[str, object]],
        page_count: int | None,
        parser: str,
    ) -> None:
        doc = await self._session.get(HubDocument, document_id)
        if doc is not None:
            doc.status = "ready"
            doc.full_text = full_text
            doc.sections = sections
            doc.page_count = page_count
            doc.parser = parser
            doc.error = None
            doc.updated_at = _now()

    async def set_summary(self, document_id: str, summary: str) -> None:
        doc = await self._session.get(HubDocument, document_id)
        if doc is not None:
            doc.summary = summary
            doc.updated_at = _now()
            await self._session.flush()

    async def mark_failed(self, document_id: str, *, error: str) -> None:
        doc = await self._session.get(HubDocument, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = error
            doc.updated_at = _now()

    async def reset_stuck_processing(self) -> int:
        result = await self._session.execute(
            select(HubDocument).where(HubDocument.status == "processing")
        )
        docs = list(result.scalars())
        for doc in docs:
            doc.status = "failed"
            doc.error = "Обработка прервана (перезапуск сервиса)"
            doc.updated_at = _now()
        return len(docs)

    async def attach(self, document_id: str, conversation_id: str) -> None:
        existing = await self._session.execute(
            select(HubDocumentAttachment).where(
                HubDocumentAttachment.document_id == document_id,
                HubDocumentAttachment.conversation_id == conversation_id,
            )
        )
        if existing.scalars().first() is not None:
            return
        self._session.add(
            HubDocumentAttachment(document_id=document_id, conversation_id=conversation_id)
        )
        await self._session.flush()

    async def detach(self, document_id: str, conversation_id: str) -> None:
        await self._session.execute(
            sa_delete(HubDocumentAttachment).where(
                HubDocumentAttachment.document_id == document_id,
                HubDocumentAttachment.conversation_id == conversation_id,
            )
        )

    async def list_for_conversation(self, conversation_id: str, owner_id: str) -> list[HubDocument]:
        result = await self._session.execute(
            select(HubDocument)
            .join(HubDocumentAttachment, HubDocumentAttachment.document_id == HubDocument.id)
            .where(
                HubDocumentAttachment.conversation_id == conversation_id,
                HubDocument.owner_id == owner_id,
            )
            .order_by(HubDocumentAttachment.created_at)
        )
        return list(result.scalars())

    async def delete(self, document_id: str) -> None:
        await self._session.execute(sa_delete(HubDocument).where(HubDocument.id == document_id))

    async def list_ready_without_summary(self) -> list[HubDocument]:
        result = await self._session.execute(
            select(HubDocument)
            .where(HubDocument.status == "ready", HubDocument.summary.is_(None))
            .order_by(HubDocument.created_at)
        )
        return list(result.scalars())
