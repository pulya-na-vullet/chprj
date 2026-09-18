"""Repository over tpl_templates (flush-not-commit)."""

from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.templates.store.models import TplTemplate

PUBLISHED = "published"


def _now() -> datetime:
    return datetime.now(UTC)


class TemplateStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def list_published(self) -> list[TplTemplate]:
        result = await self._session.execute(
            select(TplTemplate)
            .where(TplTemplate.status == PUBLISHED)
            .order_by(TplTemplate.category, TplTemplate.title)
        )
        return list(result.scalars())

    async def get_published(self, slug: str) -> TplTemplate | None:
        """Draft must read exactly like a template that doesn't exist (404)."""
        result = await self._session.execute(
            select(TplTemplate).where(
                TplTemplate.slug == slug,
                TplTemplate.status == PUBLISHED,
            )
        )
        return result.scalars().first()

    # --- операторская сторона (internal token) ---

    async def list_all(self) -> list[TplTemplate]:
        result = await self._session.execute(
            select(TplTemplate).order_by(TplTemplate.category, TplTemplate.title)
        )
        return list(result.scalars())

    async def get_by_slug(self, slug: str) -> TplTemplate | None:
        result = await self._session.execute(select(TplTemplate).where(TplTemplate.slug == slug))
        return result.scalars().first()

    async def create(
        self,
        *,
        slug: str,
        title: str,
        category: str,
        description: str,
        s3_key: str,
        fields: list[dict[str, object]],
    ) -> TplTemplate:
        row = TplTemplate(
            slug=slug,
            title=title,
            category=category,
            description=description,
            status="draft",
            s3_key=s3_key,
            fields=fields,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def touch(self, row: TplTemplate) -> None:
        row.updated_at = _now()
        await self._session.flush()

    async def delete(self, slug: str) -> None:
        await self._session.execute(sa_delete(TplTemplate).where(TplTemplate.slug == slug))
