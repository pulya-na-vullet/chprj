"""Admin proxy for the templates library (E20).

Thin wrapper over ``neurolegal.rag.templates_client`` — the ``tpl_templates``
table is owned by the templates service; this router forwards the operator
SPA's requests to its internal ``/admin/templates*`` endpoints (pattern
T-0022). Mounted alongside the other admin routers under
``settings.admin_enabled``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi import Form as FormParam

from neurolegal.contracts import (
    TEMPLATE_MAX_UPLOAD_BYTES,
    AdminTemplateOut,
    AdminTemplatePatchRequest,
    AdminTemplatesResponse,
    TemplateFileReplaceResponse,
)
from neurolegal.rag.api.deps import get_templates_client
from neurolegal.rag.templates_client import (
    DOCX_CONTENT_TYPE,
    TemplatesAuthMisconfiguredError,
    TemplatesClient,
    TemplatesClientError,
    TemplatesConflictError,
    TemplatesNotFoundError,
    TemplatesValidationError,
)

router = APIRouter(prefix="/admin/templates", tags=["admin-templates"])

_Client = Annotated[TemplatesClient, Depends(get_templates_client)]

_CHUNK_BYTES = 1024 * 1024


async def _read_capped(file: UploadFile) -> bytes:
    """Кап на прокси, не только на сервисе: /admin/* без auth by design, и
    безлимитный `file.read()` держал бы весь файл в памяти RAG-процесса ещё
    до того, как кап сработает за сетевым хопом."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > TEMPLATE_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="Файл больше 10 МБ")
        chunks.append(chunk)
    return b"".join(chunks)


def _map_error(exc: TemplatesClientError) -> HTTPException:
    if isinstance(exc, TemplatesNotFoundError):
        return HTTPException(status_code=404, detail="template_not_found")
    if isinstance(exc, TemplatesConflictError):
        return HTTPException(status_code=409, detail="slug_taken")
    if isinstance(exc, TemplatesValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, TemplatesAuthMisconfiguredError):
        return HTTPException(status_code=502, detail="templates_auth_misconfigured")
    return HTTPException(status_code=502, detail=f"templates service unavailable: {exc}")


@router.get("", response_model=AdminTemplatesResponse)
async def list_templates(client: _Client) -> AdminTemplatesResponse:
    try:
        return await client.list_templates()
    except TemplatesClientError as exc:
        raise _map_error(exc) from exc


@router.post("", response_model=AdminTemplateOut, status_code=201)
async def create_template(
    client: _Client,
    file: UploadFile,
    slug: Annotated[str, FormParam()],
    title: Annotated[str, FormParam()],
    category: Annotated[str, FormParam()],
    description: Annotated[str, FormParam()] = "",
) -> AdminTemplateOut:
    data = await _read_capped(file)
    try:
        return await client.create_template(
            slug=slug,
            title=title,
            category=category,
            description=description,
            filename=file.filename or f"{slug}.docx",
            data=data,
        )
    except TemplatesClientError as exc:
        raise _map_error(exc) from exc


@router.patch("/{slug}", response_model=AdminTemplateOut)
async def patch_template(
    slug: str, req: AdminTemplatePatchRequest, client: _Client
) -> AdminTemplateOut:
    try:
        return await client.patch_template(slug, req.model_dump(exclude_none=True))
    except TemplatesClientError as exc:
        raise _map_error(exc) from exc


@router.put("/{slug}/file", response_model=TemplateFileReplaceResponse)
async def replace_template_file(
    slug: str, file: UploadFile, client: _Client
) -> TemplateFileReplaceResponse:
    data = await _read_capped(file)
    try:
        return await client.replace_file(slug, filename=file.filename or f"{slug}.docx", data=data)
    except TemplatesClientError as exc:
        raise _map_error(exc) from exc


@router.get("/{slug}/file")
async def download_template_file(slug: str, client: _Client) -> Response:
    try:
        data = await client.download_file(slug)
    except TemplatesClientError as exc:
        raise _map_error(exc) from exc
    return Response(
        content=data,
        media_type=DOCX_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{slug}.docx"'},
    )


@router.delete("/{slug}", status_code=204)
async def delete_template(slug: str, client: _Client) -> Response:
    try:
        await client.delete_template(slug)
    except TemplatesClientError as exc:
        raise _map_error(exc) from exc
    return Response(status_code=204)
