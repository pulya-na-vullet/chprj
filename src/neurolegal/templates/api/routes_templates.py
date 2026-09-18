"""Public templates API: витрина + рендер.

Пользовательский доступ идёт через агент (`get_current_user` живёт там);
сам сервис наружу не выставляется. Видны только published-шаблоны — draft
отвечает 404, неотличимо от несуществующего.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from neurolegal.contracts import (
    RenderRequest,
    RenderValidationError,
    TemplateDetail,
    TemplateField,
    TemplateListResponse,
    TemplateSummary,
    validate_template_values,
)
from neurolegal.templates.api.deps import get_blob_store, get_store
from neurolegal.templates.config import settings
from neurolegal.templates.rendering.engine import render_docx
from neurolegal.templates.store.blob import (
    DOCX_CONTENT_TYPE,
    TemplateBlobMissingError,
    TemplatesBlobStore,
    UnsafeTemplateKeyError,
    safe_template_key,
)
from neurolegal.templates.store.models import TplTemplate
from neurolegal.templates.store.template_store import TemplateStore

router = APIRouter()

_Store = Annotated[TemplateStore, Depends(get_store)]
#: `None` when S3 credentials are absent — list/detail degrade gracefully,
#: render answers 503.
_Blob = Annotated[TemplatesBlobStore | None, Depends(get_blob_store)]

_NO_S3 = "S3 template storage is not configured (NEUROLEGAL_S3_ACCESS_KEY / _SECRET_KEY)"


def _fields(row: TplTemplate) -> list[TemplateField]:
    return [TemplateField.model_validate(f) for f in row.fields]


def _summary(row: TplTemplate) -> TemplateSummary:
    return TemplateSummary(
        slug=row.slug,
        title=row.title,
        category=row.category,
        description=row.description,
        field_count=len(row.fields),
    )


@router.get("/templates")
async def list_templates(store: _Store) -> TemplateListResponse:
    rows = await store.list_published()
    return TemplateListResponse(templates=[_summary(r) for r in rows])


@router.get("/templates/{slug}")
async def get_template(slug: str, store: _Store) -> TemplateDetail:
    row = await store.get_published(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    return TemplateDetail(**_summary(row).model_dump(), fields=_fields(row))


@router.post(
    "/templates/{slug}/render",
    responses={
        200: {
            "description": "Заполненный .docx",
            "content": {DOCX_CONTENT_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        },
        422: {"model": RenderValidationError},
    },
)
async def render_template(slug: str, body: RenderRequest, store: _Store, blob: _Blob) -> Response:
    """Детерминированная подстановка значений в шаблон.

    422 — не envelope FastAPI, но структурный `RenderValidationError`
    (список ошибок по полям), чтобы агент переспрашивал конкретные поля.
    """
    row = await store.get_published(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    errors = validate_template_values(_fields(row), body.values)
    if errors:
        return JSONResponse(
            status_code=422, content=RenderValidationError(errors=errors).model_dump()
        )
    if blob is None:
        raise HTTPException(status_code=503, detail=_NO_S3)
    try:
        key = safe_template_key(row.s3_key, settings.templates_s3_prefix)
    except UnsafeTemplateKeyError:
        # Строка в БД указывает мимо templates/-префикса общего бакета —
        # операторская ошибка данных, не повод читать чужой объект.
        raise HTTPException(status_code=500, detail="template s3_key is misconfigured") from None
    try:
        data = await blob.get(key)
    except TemplateBlobMissingError:
        raise HTTPException(status_code=503, detail="template file is unavailable") from None
    rendered = render_docx(data, body.values)
    return Response(
        content=rendered,
        media_type=DOCX_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{row.slug}.docx"'},
    )
