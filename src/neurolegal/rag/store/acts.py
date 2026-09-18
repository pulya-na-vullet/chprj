"""Catalog of distinct legislation acts present in the corpus.

Used by ``GET /acts`` for the UI source selector. Multi-part codices share a
``short_name`` (e.g. ГК РФ spans parts 1-4); we collapse to one entry and strip
the "(часть …)" suffix from the display name.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ActCatalogEntry:
    short_name: str
    full_name: str
    kind: str


_LIST_ACTS_SQL = text(
    r"""
    SELECT short_name,
           MIN(regexp_replace(full_name, '\s*\(часть[^)]*\)', '', 'g')) AS full_name,
           MIN(kind) AS kind
    FROM acts
    GROUP BY short_name
    ORDER BY short_name
    """
)


async def list_acts(session: AsyncSession) -> list[ActCatalogEntry]:
    result = await session.execute(_LIST_ACTS_SQL)
    return [
        ActCatalogEntry(short_name=row.short_name, full_name=row.full_name, kind=row.kind)
        for row in result
    ]
