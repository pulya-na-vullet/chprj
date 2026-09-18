"""Public routes over SQLite + in-memory blob (no network, no Postgres).

Draft-шаблон в каждом ответе неотличим от несуществующего (404);
422 рендера — структурный список ошибок по полям, не envelope FastAPI.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from neurolegal.templates.api.app import app
from neurolegal.templates.api.deps import get_blob_store, get_store
from neurolegal.templates.store.blob import InMemoryTemplatesBlobStore
from neurolegal.templates.store.models import Base, TplTemplate
from neurolegal.templates.store.template_store import TemplateStore
from tests.unit.templates.helpers import build_docx, document_text

ARENDA_KEY = "templates/arenda-kvartiry.docx"

FIELDS = [
    {
        "name": "landlord_fio",
        "label": "Арендодатель (ФИО)",
        "hint": None,
        "kind": "text",
        "required": True,
    },
    {"name": "start_date", "label": "Дата начала", "hint": None, "kind": "date", "required": True},
    {"name": "rent_amount", "label": "Плата", "hint": None, "kind": "money", "required": True},
    {"name": "comment", "label": "Комментарий", "hint": None, "kind": "text", "required": False},
]

VALUES = {
    "landlord_fio": "Иванов Иван Иванович",
    "start_date": "01.09.2026",
    "rent_amount": "50000",
}


@dataclass
class Ctx:
    client: AsyncClient
    blob: InMemoryTemplatesBlobStore
    maker: async_sessionmaker[AsyncSession]


def _row(
    slug: str,
    *,
    status: str = "published",
    category: str = "Договоры",
    title: str = "T",
    s3_key: str | None = None,
    fields: list[dict[str, object]] | None = None,
) -> TplTemplate:
    return TplTemplate(
        slug=slug,
        title=title,
        category=category,
        description="Описание",
        status=status,
        s3_key=s3_key or f"templates/{slug}.docx",
        fields=fields if fields is not None else [],
    )


@pytest.fixture
async def ctx() -> AsyncIterator[Ctx]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(
            _row("arenda-kvartiry", title="Аренда квартиры", s3_key=ARENDA_KEY, fields=FIELDS)
        )
        session.add(_row("uslugi", title="Оказание услуг"))
        session.add(_row("zaveshchanie", status="draft", title="Завещание"))
        await session.commit()

    blob = InMemoryTemplatesBlobStore()
    await blob.put(ARENDA_KEY, build_docx())

    async def _store() -> AsyncIterator[TemplateStore]:
        async with maker() as session:
            yield TemplateStore(session)

    app.dependency_overrides[get_store] = _store
    app.dependency_overrides[get_blob_store] = lambda: blob
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield Ctx(client=client, blob=blob, maker=maker)
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_healthz(ctx: Ctx) -> None:
    response = await ctx.client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_returns_only_published_with_field_count(ctx: Ctx) -> None:
    response = await ctx.client.get("/templates")
    assert response.status_code == 200
    templates = response.json()["templates"]
    assert [t["slug"] for t in templates] == ["arenda-kvartiry", "uslugi"]
    arenda = templates[0]
    assert arenda["title"] == "Аренда квартиры"
    assert arenda["category"] == "Договоры"
    assert arenda["field_count"] == 4


async def test_detail_returns_fields(ctx: Ctx) -> None:
    response = await ctx.client.get("/templates/arenda-kvartiry")
    assert response.status_code == 200
    body = response.json()
    assert body["field_count"] == 4
    assert [f["name"] for f in body["fields"]] == [
        "landlord_fio",
        "start_date",
        "rent_amount",
        "comment",
    ]
    assert body["fields"][1]["kind"] == "date"


@pytest.mark.parametrize("slug", ["zaveshchanie", "missing"])
async def test_detail_draft_and_missing_are_404(ctx: Ctx, slug: str) -> None:
    response = await ctx.client.get(f"/templates/{slug}")
    assert response.status_code == 404


async def test_render_returns_filled_docx(ctx: Ctx) -> None:
    response = await ctx.client.post("/templates/arenda-kvartiry/render", json={"values": VALUES})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'filename="arenda-kvartiry.docx"' in response.headers["content-disposition"]
    text = document_text(response.content)
    assert "Иванов Иван Иванович" in text
    assert "{{" not in text


async def test_render_validation_errors_are_structured(ctx: Ctx) -> None:
    values = {"start_date": "завтра", "rent_amount": "50000", "extra": "x"}
    response = await ctx.client.post("/templates/arenda-kvartiry/render", json={"values": values})
    assert response.status_code == 422
    errors = {e["field"]: e["code"] for e in response.json()["errors"]}
    assert errors == {
        "landlord_fio": "required",
        "start_date": "invalid_format",
        "extra": "unknown_field",
    }


@pytest.mark.parametrize("slug", ["zaveshchanie", "missing"])
async def test_render_draft_and_missing_are_404(ctx: Ctx, slug: str) -> None:
    response = await ctx.client.post(f"/templates/{slug}/render", json={"values": {}})
    assert response.status_code == 404


async def test_render_without_s3_is_503(ctx: Ctx) -> None:
    app.dependency_overrides[get_blob_store] = lambda: None
    response = await ctx.client.post("/templates/arenda-kvartiry/render", json={"values": VALUES})
    assert response.status_code == 503


async def test_render_with_lost_file_is_503(ctx: Ctx) -> None:
    await ctx.blob.delete(ARENDA_KEY)
    response = await ctx.client.post("/templates/arenda-kvartiry/render", json={"values": VALUES})
    assert response.status_code == 503


async def test_render_with_key_outside_prefix_is_500(ctx: Ctx) -> None:
    # Строка указывает на чужой объект общего бакета — рендер обязан отказаться
    async with ctx.maker() as session:
        session.add(_row("evil", s3_key="owner/u1/doc/original.docx"))
        await session.commit()
    response = await ctx.client.post("/templates/evil/render", json={"values": {}})
    assert response.status_code == 500
    assert ctx.blob.objects  # объект арендного шаблона не тронут, ничего не прочитано лишнего
