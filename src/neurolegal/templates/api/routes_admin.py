"""Операторский CRUD библиотеки шаблонов (за X-Internal-Token).

Токен-гейт навешивается при монтировании в app.py
(dependencies=[Depends(verify_internal_token)]); браузер сюда не ходит,
только RAG-прокси (rag/templates_client.py).
"""

import contextlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi import Form as FormParam

from neurolegal.contracts import (
    TEMPLATE_MAX_UPLOAD_BYTES,
    TEMPLATE_SLUG_RE,
    AdminTemplateOut,
    AdminTemplatePatchRequest,
    AdminTemplatesResponse,
    TemplateField,
    TemplateFileReplaceResponse,
)
from neurolegal.templates.api.deps import get_blob_store, get_store
from neurolegal.templates.config import UPLOAD_CHUNK_BYTES, settings
from neurolegal.templates.rendering.engine import default_fields, scan_placeholders
from neurolegal.templates.store.blob import (
    DOCX_CONTENT_TYPE,
    TemplateBlobMissingError,
    TemplatesBlobStore,
    UnsafeTemplateKeyError,
    safe_template_key,
    template_key,
)
from neurolegal.templates.store.models import TplTemplate
from neurolegal.templates.store.template_store import TemplateStore

router = APIRouter(prefix="/admin/templates", tags=["admin-templates"])

_Store = Annotated[TemplateStore, Depends(get_store)]
_Blob = Annotated[TemplatesBlobStore | None, Depends(get_blob_store)]

_NO_S3 = "S3 template storage is not configured (NEUROLEGAL_S3_ACCESS_KEY / _SECRET_KEY)"


def _out(row: TplTemplate) -> AdminTemplateOut:
    return AdminTemplateOut(
        slug=row.slug,
        title=row.title,
        category=row.category,
        description=row.description,
        status=row.status,
        fields=[TemplateField.model_validate(f) for f in row.fields],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_blob(blob: TemplatesBlobStore | None) -> TemplatesBlobStore:
    if blob is None:
        raise HTTPException(status_code=503, detail=_NO_S3)
    return blob


async def _read_docx_capped(file: UploadFile) -> bytes:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".docx":
        raise HTTPException(status_code=422, detail="Нужен файл .docx")
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > TEMPLATE_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="Файл больше 10 МБ")
        chunks.append(chunk)
    return b"".join(chunks)


def _scan_or_422(data: bytes) -> list[str]:
    try:
        return scan_placeholders(data)
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Не удалось разобрать шаблон: файл повреждён или Jinja-разметка некорректна",
        ) from None


def _validate_fields(fields: list[TemplateField]) -> None:
    names = [f.name for f in fields]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="Имена полей должны быть уникальны")
    for f in fields:
        if not f.name.strip() or not f.label.strip():
            raise HTTPException(status_code=422, detail="Поле без имени или подписи")


@router.get("")
async def list_templates_admin(store: _Store) -> AdminTemplatesResponse:
    rows = await store.list_all()
    return AdminTemplatesResponse(templates=[_out(r) for r in rows])


@router.post("", status_code=201)
async def create_template(
    store: _Store,
    blob: _Blob,
    file: UploadFile,
    slug: Annotated[str, FormParam()],
    title: Annotated[str, FormParam()],
    category: Annotated[str, FormParam()],
    description: Annotated[str, FormParam()] = "",
) -> AdminTemplateOut:
    if not TEMPLATE_SLUG_RE.fullmatch(slug):
        raise HTTPException(
            status_code=422,
            detail="slug: строчная латиница, цифры и дефис (например arenda-kvartiry)",
        )
    if not title.strip() or not category.strip():
        raise HTTPException(status_code=422, detail="Название и категория обязательны")
    if await store.get_by_slug(slug) is not None:
        raise HTTPException(status_code=409, detail="slug_taken")
    storage = _require_blob(blob)
    data = await _read_docx_capped(file)
    names = _scan_or_422(data)
    key = template_key(slug, settings.templates_s3_prefix)
    # S3 раньше БД: упавшая заливка не должна оставить строку без байтов.
    await storage.put(key, data)
    row = await store.create(
        slug=slug,
        title=title.strip(),
        category=category.strip(),
        description=description.strip(),
        s3_key=key,
        fields=[f.model_dump() for f in default_fields(names)],
    )
    await store.commit()
    return _out(row)


@router.patch("/{slug}")
async def patch_template(
    slug: str, body: AdminTemplatePatchRequest, store: _Store
) -> AdminTemplateOut:
    row = await store.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(status_code=422, detail="Название не может быть пустым")
        row.title = body.title.strip()
    if body.category is not None:
        if not body.category.strip():
            raise HTTPException(status_code=422, detail="Категория не может быть пустой")
        row.category = body.category.strip()
    if body.description is not None:
        row.description = body.description.strip()
    if body.status is not None:
        row.status = body.status
    if body.fields is not None:
        _validate_fields(body.fields)
        row.fields = [f.model_dump() for f in body.fields]
    await store.touch(row)
    await store.commit()
    return _out(row)


@router.put("/{slug}/file")
async def replace_template_file(
    slug: str, file: UploadFile, store: _Store, blob: _Blob
) -> TemplateFileReplaceResponse:
    row = await store.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    storage = _require_blob(blob)
    data = await _read_docx_capped(file)
    names = _scan_or_422(data)
    existing = [TemplateField.model_validate(f) for f in row.fields]
    existing_names = {f.name for f in existing}
    added = [n for n in names if n not in existing_names]
    # Осиротевшие остаются в fields — оператор сам решает, удалять ли
    # (PATCH новым списком без них); UI подсвечивает их по этому ответу.
    orphaned = sorted(existing_names - set(names))
    merged = existing + default_fields(added)
    try:
        key = safe_template_key(row.s3_key, settings.templates_s3_prefix)
    except UnsafeTemplateKeyError:
        raise HTTPException(status_code=500, detail="template s3_key is misconfigured") from None
    await storage.put(key, data)
    row.fields = [f.model_dump() for f in merged]
    await store.touch(row)
    await store.commit()
    return TemplateFileReplaceResponse(template=_out(row), added=added, orphaned=orphaned)


@router.get("/{slug}/file")
async def download_template_file(slug: str, store: _Store, blob: _Blob) -> Response:
    row = await store.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    storage = _require_blob(blob)
    try:
        key = safe_template_key(row.s3_key, settings.templates_s3_prefix)
    except UnsafeTemplateKeyError:
        raise HTTPException(status_code=500, detail="template s3_key is misconfigured") from None
    try:
        data = await storage.get(key)
    except TemplateBlobMissingError:
        raise HTTPException(status_code=503, detail="template file is unavailable") from None
    return Response(
        content=data,
        media_type=DOCX_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{row.slug}.docx"'},
    )


@router.delete("/{slug}", status_code=204)
async def delete_template(slug: str, store: _Store, blob: _Blob) -> Response:
    row = await store.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    if blob is not None:
        # Мусорный ключ мимо префикса не трогаем — строку всё равно удаляем.
        with contextlib.suppress(UnsafeTemplateKeyError):
            await blob.delete(safe_template_key(row.s3_key, settings.templates_s3_prefix))
    await store.delete(slug)
    await store.commit()
    return Response(status_code=204)
