"""Client-facing DTOs for the templates service (neurolegal-templates-api).

Single source of truth for the service's HTTP boundary; the service and any
HTTP client both import these. Values are always strings: the agent collects
answers as text and the service validates format by field ``kind``.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TemplateStatus = Literal["draft", "published"]
TemplateFieldKind = Literal["text", "date", "money", "number"]
RenderErrorCode = Literal["required", "invalid_format", "unknown_field"]

#: Slug живёт в URL и в S3-ключе (``templates/<slug>.docx``) — только строчная
#: латиница/цифры/дефис, чтобы ключ не мог выйти за префикс и не требовал
#: URL-кодирования.
TEMPLATE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: Кап загрузки шаблона живёт в contracts, потому что применять этот кап
#: обязана каждая сторона пути «RAG-прокси → templates-сервис»: прокси не
#: должен удерживать в памяти безлимитный файл, полагаясь на кап за сетевым
#: хопом.
TEMPLATE_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class TemplateField(BaseModel):
    """One ``{{ placeholder }}`` of a .docx template with operator metadata.

    A fresh scan yields ``label = name`` / ``kind = text`` / ``required = True``;
    the operator refines label/hint/kind by hand (they drive the questions the
    agent asks).
    """

    name: str
    label: str
    hint: str | None = None
    kind: TemplateFieldKind = "text"
    required: bool = True


class TemplateSummary(BaseModel):
    slug: str
    title: str
    category: str
    description: str
    field_count: int


class TemplateDetail(TemplateSummary):
    fields: list[TemplateField]


class TemplateListResponse(BaseModel):
    templates: list[TemplateSummary]


class RenderRequest(BaseModel):
    values: dict[str, str]


class RenderFieldError(BaseModel):
    field: str
    code: RenderErrorCode
    message: str


_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")
_MONEY_RE = re.compile(r"^\d+(?:[.,]\d{1,2})?$")
_NUMBER_RE = re.compile(r"^-?\d+$")

_KIND_MESSAGES = {
    "date": "Ожидается дата в формате ДД.ММ.ГГГГ",
    "money": "Ожидается сумма числом, например 50000 или 50000,50",
    "number": "Ожидается целое число",
}


def _strip_spaces(value: str) -> str:
    # «50 000,50»: обычный или неразрывный пробел внутри суммы — валидный ввод
    return value.replace(" ", "").replace(" ", "")


def _kind_ok(kind: str, value: str) -> bool:
    if kind == "date":
        for fmt in _DATE_FORMATS:
            try:
                datetime.strptime(value, fmt)
            except ValueError:
                continue
            return True
        return False
    if kind == "money":
        return _MONEY_RE.fullmatch(_strip_spaces(value)) is not None
    if kind == "number":
        return _NUMBER_RE.fullmatch(_strip_spaces(value)) is not None
    return True  # text — любой непустой ввод


def validate_template_values(
    fields: Sequence[TemplateField], values: Mapping[str, str]
) -> list[RenderFieldError]:
    """Валидация значений против полей шаблона — единый источник правды.

    Живёт в contracts, потому что одну и ту же проверку обязаны выполнять
    рендер на templates-сервисе и stage_template на стороне агента (E20 §6):
    разошедшиеся копии дали бы черновик, который сервис отказывается
    рендерить. Структурные ошибки по полям — агент переспрашивает ровно их.
    """
    errors: list[RenderFieldError] = []
    known = {f.name for f in fields}
    for name in values:
        if name not in known:
            errors.append(
                RenderFieldError(
                    field=name, code="unknown_field", message="Неизвестное поле шаблона"
                )
            )
    for field in fields:
        value = (values.get(field.name) or "").strip()
        if not value:
            if field.required:
                errors.append(
                    RenderFieldError(
                        field=field.name, code="required", message="Обязательное поле не заполнено"
                    )
                )
            continue
        if not _kind_ok(field.kind, value):
            errors.append(
                RenderFieldError(
                    field=field.name,
                    code="invalid_format",
                    message=_KIND_MESSAGES.get(field.kind, "Неверный формат значения"),
                )
            )
    return errors


class RenderValidationError(BaseModel):
    """422 body of ``POST /templates/{slug}/render`` — no ``detail`` envelope."""

    errors: list[RenderFieldError]


class AdminTemplateOut(BaseModel):
    """Operator view: full field list and status, drafts included."""

    slug: str
    title: str
    category: str
    description: str
    status: TemplateStatus
    fields: list[TemplateField]
    created_at: datetime
    updated_at: datetime


class AdminTemplatesResponse(BaseModel):
    templates: list[AdminTemplateOut]


class AdminTemplatePatchRequest(BaseModel):
    """Partial update: absent field means "leave unchanged". ``fields``
    replaces the whole list — this is how the operator refines label/hint/kind
    and drops orphaned entries after a file replace."""

    title: str | None = None
    category: str | None = None
    description: str | None = None
    status: TemplateStatus | None = None
    fields: list[TemplateField] | None = None


class TemplateFileReplaceResponse(BaseModel):
    """Re-scan outcome of ``PUT /admin/templates/{slug}/file``: new placeholder
    names got default fields, disappeared ones stay in ``fields`` but are
    reported as ``orphaned`` so the admin UI can offer to drop them."""

    template: AdminTemplateOut
    added: list[str]
    orphaned: list[str]
