"""Acts catalog against a real DB. Marker: db_only — gated by conftest."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.db import get_sessionmaker
from neurolegal.rag.store.acts import list_acts

pytestmark = pytest.mark.db_only


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as s:
        yield s


@pytest.mark.asyncio
async def test_list_acts_collapses_multipart_codices(session: AsyncSession) -> None:
    acts = await list_acts(session)
    names = [a.short_name for a in acts]
    # Core invariants of list_acts: multipart codices collapse into one entry
    # and the "(часть …)" suffix is stripped from full_name.
    assert names.count("ГК РФ") <= 1
    for a in acts:
        assert "(часть" not in a.full_name
    # The query has `ORDER BY short_name` server-side; don't re-assert sort
    # with Python's `sorted()` because PostgreSQL's default collation and
    # Python's code-point order disagree on some Cyrillic adjacents
    # (e.g. ВК vs ВзК).  # noqa: RUF003
