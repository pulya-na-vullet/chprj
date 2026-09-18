"""TemplateStore over in-memory SQLite: published-only reads, ordering."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.templates.store.models import Base, TplTemplate
from neurolegal.templates.store.template_store import TemplateStore


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _row(slug: str, *, status: str, category: str = "Договоры", title: str = "T") -> TplTemplate:
    return TplTemplate(
        slug=slug,
        title=title,
        category=category,
        description="",
        status=status,
        s3_key=f"templates/{slug}.docx",
        fields=[],
    )


async def test_list_published_filters_and_orders(session) -> None:
    store = TemplateStore(session)
    session.add(_row("z-draft", status="draft"))
    session.add(_row("uslugi", status="published", title="Оказание услуг"))
    session.add(_row("arenda", status="published", title="Аренда квартиры"))
    session.add(_row("doverennost", status="published", category="Личные документы", title="А"))
    await store.commit()

    rows = await store.list_published()
    assert [(r.category, r.title) for r in rows] == [
        ("Договоры", "Аренда квартиры"),
        ("Договоры", "Оказание услуг"),
        ("Личные документы", "А"),
    ]


async def test_get_published_hides_draft_and_missing(session) -> None:
    store = TemplateStore(session)
    session.add(_row("arenda", status="published"))
    session.add(_row("zaveshchanie", status="draft"))
    await store.commit()

    found = await store.get_published("arenda")
    assert found is not None and found.slug == "arenda"
    assert await store.get_published("zaveshchanie") is None
    assert await store.get_published("missing") is None
