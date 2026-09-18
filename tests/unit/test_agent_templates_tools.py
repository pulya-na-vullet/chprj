"""Тулзы шаблонов: stage-валидация, инвариант stage→render, деградация.

Клиенты — фейки; черновики — настоящий ConversationStore поверх SQLite.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.chat.events import DocumentReadyEvent, TemplateDraftEvent
from neurolegal.agent.chat.tools.base import ToolContext
from neurolegal.agent.chat.tools.templates import (
    handle_list_templates,
    handle_render_template,
    handle_stage_template,
)
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.agent.tools.templates_client import (
    TemplateRenderInvalidError,
    TemplatesClientError,
    TemplatesNotFoundError,
)
from neurolegal.contracts import (
    HubDocumentInfo,
    RenderFieldError,
    TemplateDetail,
    TemplateField,
    TemplateSummary,
    ToolsSettings,
)

USER_ID = "u1"

DETAIL = TemplateDetail(
    slug="arenda-kvartiry",
    title="Аренда квартиры",
    category="Договоры",
    description="",
    field_count=3,
    fields=[
        TemplateField(name="landlord_fio", label="Арендодатель"),
        TemplateField(name="rent", label="Плата", kind="money"),
        TemplateField(name="comment", label="Комментарий", required=False),
    ],
)

VALID_VALUES = {"landlord_fio": "Иванов И. И.", "rent": "50000"}


class FakeTemplatesClient:
    def __init__(self) -> None:
        self.render_calls: list[tuple[str, dict[str, str]]] = []
        self.fail_with: Exception | None = None
        self.render_fail_with: Exception | None = None

    async def list_templates(self) -> list[TemplateSummary]:
        if self.fail_with:
            raise self.fail_with
        return [TemplateSummary(**DETAIL.model_dump(exclude={"fields"}))]

    async def get_template(self, slug: str) -> TemplateDetail:
        if self.fail_with:
            raise self.fail_with
        if slug != DETAIL.slug:
            raise TemplatesNotFoundError(slug)
        return DETAIL

    async def render(self, slug: str, values: dict[str, str]) -> bytes:
        if self.render_fail_with:
            raise self.render_fail_with
        self.render_calls.append((slug, dict(values)))
        return b"PK-docx-bytes"


class FakeDocumentsClient:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, str, str]] = []  # (filename, content_type, owner)
        self.attached: list[tuple[str, str, str]] = []
        self.fail = False
        self.fail_attach = False

    async def upload(self, data, filename, content_type, *, owner_id):  # type: ignore[no-untyped-def]
        if self.fail:
            from neurolegal.agent.tools.documents_client import DocumentsClientError

            raise DocumentsClientError("hub down")
        self.uploaded.append((filename, content_type, owner_id))
        return HubDocumentInfo(
            id=f"doc-{len(self.uploaded)}",
            owner_id=owner_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            status="processing",
            parser="docx",
            created_at=datetime.now(UTC),
        )

    async def attach(self, document_id, conversation_id, user_id):  # type: ignore[no-untyped-def]
        if self.fail_attach:
            from neurolegal.agent.tools.documents_client import DocumentsClientError

            raise DocumentsClientError("attach failed")
        self.attached.append((document_id, conversation_id, user_id))


@pytest_asyncio.fixture
async def env() -> AsyncIterator[tuple[ToolContext, ConversationStore, str]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        store = ConversationStore(session)
        conv_id = await store.create_conversation(USER_ID)
        await store.commit()
        ctx = ToolContext(
            rag_client=object(),  # type: ignore[arg-type]
            acts=None,
            tools=ToolsSettings(),
            documents_client=FakeDocumentsClient(),  # type: ignore[arg-type]
            user_id=USER_ID,
            templates_client=FakeTemplatesClient(),  # type: ignore[arg-type]
            conversation_store=store,
            conversation_id=conv_id,
        )
        yield ctx, store, conv_id
    await engine.dispose()


def _result(outcome) -> dict:  # type: ignore[no-untyped-def]
    return json.loads(outcome.tool_result)


async def test_stage_persists_draft_and_emits_summary(env) -> None:  # type: ignore[no-untyped-def]
    ctx, store, conv_id = env
    outcome = await handle_stage_template(
        {
            "template_slug": DETAIL.slug,
            "values": VALID_VALUES,
            "sources": {"landlord_fio": "profile", "rent": "user"},
        },
        ctx,
    )
    assert _result(outcome)["status"] == "staged"
    draft = await store.get_template_draft(conv_id)
    assert draft is not None
    assert draft.values == VALID_VALUES
    assert draft.sources == {"landlord_fio": "profile", "rent": "user"}
    assert draft.rendered_at is None
    assert len(outcome.events) == 1
    event = outcome.events[0]
    assert isinstance(event, TemplateDraftEvent)
    rows = [(f.name, f.value, f.source) for f in event.fields]
    # порядок полей шаблона; пустой необязательный comment скрыт
    assert rows == [
        ("landlord_fio", "Иванов И. И.", "profile"),
        ("rent", "50000", "user"),
    ]


_STAGE_ARGS = {
    "template_slug": DETAIL.slug,
    "values": VALID_VALUES,
    "sources": {"landlord_fio": "profile", "rent": "user"},
}


async def test_restage_unchanged_suppresses_summary_event(env) -> None:  # type: ignore[no-untyped-def]
    # T-0142: модель пере-stage'ит перед render «на всякий случай» — вторая
    # одинаковая карточка сводки в ленте не нужна.
    ctx, store, conv_id = env
    first = await handle_stage_template(dict(_STAGE_ARGS), ctx)
    assert len(first.events) == 1
    second = await handle_stage_template(dict(_STAGE_ARGS), ctx)
    assert _result(second)["status"] == "unchanged"
    assert second.events == []
    draft = await store.get_template_draft(conv_id)
    assert draft is not None and draft.values == VALID_VALUES


async def test_restage_with_changed_values_emits_again(env) -> None:  # type: ignore[no-untyped-def]
    ctx, _store, _conv_id = env
    await handle_stage_template(dict(_STAGE_ARGS), ctx)
    changed = dict(_STAGE_ARGS) | {"values": {**VALID_VALUES, "rent": "60000"}}
    outcome = await handle_stage_template(changed, ctx)
    assert _result(outcome)["status"] == "staged"
    assert len(outcome.events) == 1


async def test_restage_after_render_emits_again(env) -> None:  # type: ignore[no-untyped-def]
    # Черновик уже отрендерен — новый цикл заполнения легитимно
    # показывает сводку заново, даже при неизменных данных.
    ctx, store, conv_id = env
    await handle_stage_template(dict(_STAGE_ARGS), ctx)
    await store.mark_template_rendered(conv_id)
    outcome = await handle_stage_template(dict(_STAGE_ARGS), ctx)
    assert _result(outcome)["status"] == "staged"
    assert len(outcome.events) == 1


async def test_stage_invalid_values_returns_errors_and_writes_nothing(env) -> None:  # type: ignore[no-untyped-def]
    ctx, store, conv_id = env
    outcome = await handle_stage_template(
        {"template_slug": DETAIL.slug, "values": {"rent": "дорого", "extra": "x"}},
        ctx,
    )
    errors = {e["field"]: e["code"] for e in _result(outcome)["errors"]}
    assert errors == {
        "landlord_fio": "required",
        "rent": "invalid_format",
        "extra": "unknown_field",
    }
    assert outcome.events == []
    assert await store.get_template_draft(conv_id) is None


async def test_stage_unknown_slug_and_outage(env) -> None:  # type: ignore[no-untyped-def]
    ctx, _store, _conv = env
    missing = await handle_stage_template({"template_slug": "nope", "values": {}}, ctx)
    assert "error" in _result(missing)
    ctx.templates_client.fail_with = TemplatesClientError("down")
    down = await handle_stage_template({"template_slug": DETAIL.slug, "values": {}}, ctx)
    assert down.unavailable and "error" in _result(down)


async def test_render_uses_staged_values_not_llm_arguments(env) -> None:  # type: ignore[no-untyped-def]
    ctx, store, conv_id = env
    await handle_stage_template({"template_slug": DETAIL.slug, "values": VALID_VALUES}, ctx)
    # Модель пытается подменить значения аргументами — они игнорируются
    outcome = await handle_render_template(
        {"values": {"landlord_fio": "ЗЛОУМЫШЛЕННИК", "rent": "1"}}, ctx
    )
    assert _result(outcome)["status"] == "ok"
    assert ctx.templates_client.render_calls == [(DETAIL.slug, VALID_VALUES)]
    # документ ушёл в библиотеку владельца и привязан к беседе
    docs = ctx.documents_client
    assert docs.uploaded == [
        (
            "Аренда квартиры.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            USER_ID,
        )
    ]
    assert docs.attached == [("doc-1", conv_id, USER_ID)]
    event = outcome.events[0]
    assert isinstance(event, DocumentReadyEvent)
    assert (event.document_id, event.fields_filled) == ("doc-1", 2)
    draft = await store.get_template_draft(conv_id)
    assert draft is not None and draft.rendered_at is not None


async def test_render_without_draft_is_honest_error(env) -> None:  # type: ignore[no-untyped-def]
    ctx, _store, _conv = env
    outcome = await handle_render_template({}, ctx)
    assert "error" in _result(outcome)
    assert ctx.documents_client.uploaded == []


async def test_render_hub_down_keeps_draft_renderable(env) -> None:  # type: ignore[no-untyped-def]
    ctx, store, conv_id = env
    await handle_stage_template({"template_slug": DETAIL.slug, "values": VALID_VALUES}, ctx)
    ctx.documents_client.fail = True
    outcome = await handle_render_template({}, ctx)
    assert "error" in _result(outcome)
    draft = await store.get_template_draft(conv_id)
    assert draft is not None and draft.rendered_at is None  # повторный render безопасен
    ctx.documents_client.fail = False
    retry = await handle_render_template({}, ctx)
    assert _result(retry)["status"] == "ok"


async def test_second_render_does_not_create_second_document(env) -> None:  # type: ignore[no-untyped-def]
    """T-0143: модель склонна перевызывать тулзы «на всякий случай» — второй
    render того же черновика обязан вернуть уже готовый документ и не
    загружать в библиотеку дубликат (и не показывать вторую карточку)."""
    ctx, _store, _conv_id = env
    await handle_stage_template({"template_slug": DETAIL.slug, "values": VALID_VALUES}, ctx)
    first = await handle_render_template({}, ctx)
    assert _result(first)["status"] == "ok"

    second = await handle_render_template({}, ctx)
    assert _result(second)["status"] == "already_rendered"
    assert _result(second)["document_id"] == "doc-1"
    assert len(ctx.documents_client.uploaded) == 1
    assert len(ctx.templates_client.render_calls) == 1
    assert second.events == []  # вторая карточка документа в ленте не нужна


async def test_attach_failure_reuses_uploaded_document(env) -> None:  # type: ignore[no-untyped-def]
    """T-0143: upload прошёл, attach упал — повторный render переиспользует
    загруженный документ, иначе в библиотеке остаётся файл-сирота."""
    ctx, store, conv_id = env
    await handle_stage_template({"template_slug": DETAIL.slug, "values": VALID_VALUES}, ctx)
    ctx.documents_client.fail_attach = True

    failed = await handle_render_template({}, ctx)
    assert "error" in _result(failed)
    assert len(ctx.documents_client.uploaded) == 1
    draft = await store.get_template_draft(conv_id)
    assert draft is not None and draft.rendered_at is None
    assert draft.document_id == "doc-1"  # id сохранён до attach

    ctx.documents_client.fail_attach = False
    retry = await handle_render_template({}, ctx)
    assert _result(retry)["status"] == "ok"
    assert len(ctx.documents_client.uploaded) == 1  # второй загрузки не было
    assert ctx.documents_client.attached == [("doc-1", conv_id, USER_ID)]
    event = retry.events[0]
    assert isinstance(event, DocumentReadyEvent) and event.document_id == "doc-1"


async def test_restage_after_render_clears_previous_document(env) -> None:  # type: ignore[no-untyped-def]
    """Новые данные — новый цикл: следующий render обязан сформировать новый
    документ, не возвращая предыдущий."""
    ctx, store, conv_id = env
    await handle_stage_template({"template_slug": DETAIL.slug, "values": VALID_VALUES}, ctx)
    await handle_render_template({}, ctx)

    changed = {"template_slug": DETAIL.slug, "values": {**VALID_VALUES, "rent": "60000"}}
    await handle_stage_template(changed, ctx)
    draft = await store.get_template_draft(conv_id)
    assert draft is not None and draft.document_id is None and draft.rendered_at is None

    again = await handle_render_template({}, ctx)
    assert _result(again)["status"] == "ok"
    assert len(ctx.documents_client.uploaded) == 2


async def test_render_validation_errors_pass_through(env) -> None:  # type: ignore[no-untyped-def]
    ctx, _store, _conv = env
    await handle_stage_template({"template_slug": DETAIL.slug, "values": VALID_VALUES}, ctx)
    ctx.templates_client.render_fail_with = TemplateRenderInvalidError(
        [RenderFieldError(field="rent", code="invalid_format", message="Ожидается сумма")]
    )
    outcome = await handle_render_template({}, ctx)
    assert _result(outcome)["errors"][0]["field"] == "rent"


async def test_list_templates_degrades_honestly(env) -> None:  # type: ignore[no-untyped-def]
    ctx, _store, _conv = env
    ok = await handle_list_templates({}, ctx)
    assert _result(ok)["templates"][0]["slug"] == DETAIL.slug
    ctx.templates_client.fail_with = TemplatesClientError("down")
    down = await handle_list_templates({}, ctx)
    assert down.unavailable and "error" in _result(down)
