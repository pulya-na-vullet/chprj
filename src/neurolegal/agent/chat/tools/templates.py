"""Тулзы шаблонного флоу (E20, спека §6): list_templates / stage_template /
render_template.

Двухфазный инвариант доверия: stage_template валидирует значения и сохраняет
черновик на сервере (template_drafts, один на беседу), render_template не
принимает значений от модели — рендерится ровно сохранённый черновик. LLM не
может подменить данные между подтверждением пользователя и рендером.
"""

import json
import logging
from collections.abc import Mapping

from neurolegal.agent.chat.events import DocumentReadyEvent, TemplateDraftEvent
from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.agent.tools.documents_client import DocumentsClientError
from neurolegal.agent.tools.templates_client import (
    TemplateRenderInvalidError,
    TemplatesClientError,
    TemplatesNotFoundError,
)
from neurolegal.contracts import (
    TemplateDraftFieldOut,
    TemplateField,
    validate_template_values,
)

logger = logging.getLogger(__name__)

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_UNAVAILABLE = {"error": "Сервис шаблонов недоступен, попробуйте позже"}
_NOT_FOUND = {"error": "Шаблон не найден или снят с публикации"}
_HUB_DOWN = "Библиотека документов недоступна — документ не сохранён, попробуйте ещё раз"
# После upload документ уже лежит в «Файлах» — обещать обратное нельзя,
# незавершённой осталась только привязка к беседе.
_ATTACH_DOWN = (
    "Документ сформирован и сохранён в «Файлы», но не прикреплён к беседе — попробуйте ещё раз"
)

LIST_TEMPLATES_TOOL = ToolSpec(
    name="list_templates",
    description=(
        "Список доступных шаблонов документов (slug, название, категория, "
        "описание, число полей). Вызывай, когда пользователь просит составить "
        "документ, чтобы предложить подходящий шаблон."
    ),
    parameters={"type": "object", "properties": {}},
)

STAGE_TEMPLATE_TOOL = ToolSpec(
    name="stage_template",
    description=(
        "Сохранить собранные значения полей шаблона как черновик и показать "
        "пользователю сводку на подтверждение. values — имя поля → значение "
        "строкой; sources — имя поля → откуда значение: profile (из профиля/"
        "контекста), document (из приложенного документа), user (пользователь "
        "назвал сам). Повторный вызов перезаписывает черновик."
    ),
    parameters={
        "type": "object",
        "properties": {
            "template_slug": {"type": "string", "description": "Slug шаблона."},
            "values": {
                "type": "object",
                "description": "Значения полей: имя → строка.",
                "additionalProperties": {"type": "string"},
            },
            "sources": {
                "type": "object",
                "description": "Происхождение значений: имя поля → profile|document|user.",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["template_slug", "values"],
    },
)

RENDER_TEMPLATE_TOOL = ToolSpec(
    name="render_template",
    description=(
        "Сформировать документ из подтверждённого черновика. Без аргументов: "
        "рендерится ровно тот черновик, что показан пользователю в сводке. "
        "Вызывай только после явного подтверждения пользователя."
    ),
    parameters={"type": "object", "properties": {}},
)


def _err(payload: Mapping[str, object], *, unavailable: bool = False) -> ToolOutcome:
    return ToolOutcome(json.dumps(payload, ensure_ascii=False), unavailable=unavailable)


async def handle_list_templates(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    if ctx.templates_client is None:
        return _err(_UNAVAILABLE, unavailable=True)
    try:
        templates = await ctx.templates_client.list_templates()
    except TemplatesClientError:
        return _err(_UNAVAILABLE, unavailable=True)
    payload = {"templates": [t.model_dump() for t in templates]}
    return ToolOutcome(json.dumps(payload, ensure_ascii=False))


def _clean_values(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


_VALID_SOURCES = frozenset({"profile", "document", "user"})


def _clean_sources(raw: object, values: dict[str, str]) -> dict[str, str]:
    """Метка происхождения на каждое значение; всё непонятное — user."""
    raw_map = raw if isinstance(raw, dict) else {}
    return {
        name: (str(raw_map.get(name)) if str(raw_map.get(name)) in _VALID_SOURCES else "user")
        for name in values
    }


def _draft_fields(
    fields: list[TemplateField], values: dict[str, str], sources: dict[str, str]
) -> list[TemplateDraftFieldOut]:
    """Строки сводки в порядке полей шаблона; незаполненные необязательные
    поля не показываются."""
    out: list[TemplateDraftFieldOut] = []
    for f in fields:
        value = (values.get(f.name) or "").strip()
        if not value and not f.required:
            continue
        out.append(
            TemplateDraftFieldOut(
                name=f.name,
                label=f.label,
                value=value,
                source=sources.get(f.name, "user"),
            )
        )
    return out


async def handle_stage_template(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    if ctx.templates_client is None or ctx.conversation_store is None:
        return _err(_UNAVAILABLE, unavailable=True)
    slug = str(arguments.get("template_slug", "")).strip()
    if not slug:
        return _err({"error": "stage_template требует template_slug"})
    try:
        detail = await ctx.templates_client.get_template(slug)
    except TemplatesNotFoundError:
        return _err(_NOT_FOUND)
    except TemplatesClientError:
        return _err(_UNAVAILABLE, unavailable=True)

    values = _clean_values(arguments.get("values"))
    sources = _clean_sources(arguments.get("sources"), values)
    errors = validate_template_values(detail.fields, values)
    if errors:
        # Структурная ошибка модели: черновик не пишется, сводка не показывается.
        return _err({"errors": [e.model_dump() for e in errors]})

    # Модели свойственно пере-stage'ить перед render «на всякий случай» —
    # при неизменных данных это давало вторую карточку сводки в ленте
    # (T-0142). Неизменившийся неотрендеренный черновик того же шаблона не
    # эмитит событие; после рендера или при новых данных цикл начинается заново.
    existing = await ctx.conversation_store.get_template_draft(ctx.conversation_id)
    if (
        existing is not None
        and existing.rendered_at is None
        and existing.template_slug == slug
        and existing.values == dict(values)
        and existing.sources == dict(sources)
    ):
        unchanged = {
            "status": "unchanged",
            "template": slug,
            "note": "Черновик не изменился — сводка уже показана пользователю. "
            "Не показывай её снова: попроси подтверждение (ask_user) или, если "
            "оно уже получено, вызови render_template.",
        }
        return ToolOutcome(json.dumps(unchanged, ensure_ascii=False))

    await ctx.conversation_store.upsert_template_draft(
        ctx.conversation_id,
        slug=slug,
        title=detail.title,
        values=dict(values),
        sources=dict(sources),
    )
    await ctx.conversation_store.commit()
    event = TemplateDraftEvent(
        slug=slug,
        title=detail.title,
        fields=_draft_fields(detail.fields, values, sources),
    )
    result = {
        "status": "staged",
        "template": slug,
        "filled": len([v for v in values.values() if v.strip()]),
        "note": "Черновик сохранён и показан пользователю. Попроси подтверждение "
        "(ask_user) и только после согласия вызови render_template.",
    }
    return ToolOutcome(json.dumps(result, ensure_ascii=False), events=[event])


async def handle_render_template(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    if ctx.templates_client is None or ctx.conversation_store is None:
        return _err(_UNAVAILABLE, unavailable=True)
    draft = await ctx.conversation_store.get_template_draft(ctx.conversation_id)
    if draft is None or not draft.values:
        return _err({"error": "Нет сохранённого черновика — сначала stage_template"})
    if ctx.documents_client is None:
        return _err({"error": "Библиотека документов недоступна, попробуйте позже"})

    # Черновик уже отрендерен: модели свойственно перевызвать тулзу «на всякий
    # случай» (та же природа, что и пере-stage в T-0142), но здесь цена ошибки
    # выше — второй файл в библиотеке пользователя. Карточку тоже не
    # повторяем: документ уже показан. Новые данные снимают rendered_at
    # (upsert_template_draft) — тогда цикл начинается заново.
    if draft.rendered_at is not None:
        done = {
            "status": "already_rendered",
            "document_id": draft.document_id,
            "filename": draft.document_filename,
            "note": "Документ по этому черновику уже сформирован и лежит в «Файлах» — "
            "не рендери повторно. Если нужны правки, собери новые значения "
            "и вызови stage_template заново.",
        }
        return ToolOutcome(json.dumps(done, ensure_ascii=False))

    filename = draft.document_filename or f"{draft.template_title}.docx"
    values = {str(k): str(v) for k, v in draft.values.items()}
    document_id = draft.document_id

    # Оборванная прошлая попытка (upload прошёл, attach упал) — документ уже
    # в библиотеке владельца, осталась привязка. Рендерить и грузить заново
    # значило бы оставить сироту.
    if document_id is None:
        # Инвариант: аргументы модели игнорируются, рендерятся ровно staged-значения.
        try:
            rendered = await ctx.templates_client.render(draft.template_slug, values)
        except TemplateRenderInvalidError as exc:
            return _err({"errors": [e.model_dump() for e in exc.errors]})
        except TemplatesNotFoundError:
            return _err(_NOT_FOUND)
        except TemplatesClientError:
            return _err(_UNAVAILABLE, unavailable=True)
        try:
            doc = await ctx.documents_client.upload(
                rendered, filename, DOCX_CONTENT_TYPE, owner_id=ctx.user_id
            )
        except DocumentsClientError:
            return _err({"error": _HUB_DOWN})
        document_id, filename = doc.id, doc.filename
        # Фиксируем до привязки — это и делает повторный вызов безопасным.
        await ctx.conversation_store.record_template_document(
            ctx.conversation_id, document_id=document_id, filename=filename
        )
        await ctx.conversation_store.commit()

    try:
        await ctx.documents_client.attach(document_id, ctx.conversation_id, ctx.user_id)
    except DocumentsClientError:
        return _err({"error": _ATTACH_DOWN})

    await ctx.conversation_store.mark_template_rendered(ctx.conversation_id)
    await ctx.conversation_store.commit()
    fields_filled = len([v for v in values.values() if v.strip()])
    event = DocumentReadyEvent(
        document_id=document_id, filename=filename, fields_filled=fields_filled
    )
    result = {
        "status": "ok",
        "document_id": document_id,
        "filename": filename,
        "note": "Документ сохранён в «Файлы» и прикреплён к беседе. Сообщи об этом кратко.",
    }
    return ToolOutcome(json.dumps(result, ensure_ascii=False), events=[event])
