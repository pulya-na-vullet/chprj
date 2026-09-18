"""HTTP client from the RAG service to the templates service's operator API.

The RAG admin surface talks to the templates service **only** through this
client — never by importing ``neurolegal.templates.*`` modules directly
(boundary guard). Pattern mirrors ``rag/agent_client.py`` (T-0022): retries
only idempotent reads; create/replace are not retried, чтобы сетевой таймаут
не обернулся дублем загрузки.
"""

import contextlib
from typing import Any

import httpx

from neurolegal.contracts import (
    AdminTemplateOut,
    AdminTemplatesResponse,
    TemplateFileReplaceResponse,
)
from neurolegal.core.http import make_http_retry

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TemplatesClientError(RuntimeError):
    pass


class TemplatesNotFoundError(TemplatesClientError):
    """404 for a specific slug — distinct from a generic outage."""


class TemplatesAuthMisconfiguredError(TemplatesClientError):
    """401 — the internal token is missing or wrong on this service."""


class TemplatesConflictError(TemplatesClientError):
    """409 — slug already taken."""


class TemplatesValidationError(TemplatesClientError):
    """422 from the service (bad slug/file/fields) — carries the detail text
    so the operator sees the actual reason, not a generic 502."""


def _raise_for_common(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise TemplatesAuthMisconfiguredError("templates service rejected internal token")
    if response.status_code == 404:
        raise TemplatesNotFoundError("template not found")
    if response.status_code == 409:
        raise TemplatesConflictError("slug_taken")
    if response.status_code == 422:
        detail: object = response.text
        with contextlib.suppress(ValueError):
            detail = response.json().get("detail", detail)
        raise TemplatesValidationError(str(detail))
    response.raise_for_status()


class TemplatesClient:
    """Thin wrapper over the templates service's ``/admin/templates*`` API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8003",
        timeout: float = 30.0,
        internal_token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._internal_token = internal_token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._internal_token:
            headers["X-Internal-Token"] = self._internal_token
        return headers

    async def list_templates(self) -> AdminTemplatesResponse:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/admin/templates", headers=self._headers()
                        )
                        _raise_for_common(response)
                        payload = response.json()
                    return AdminTemplatesResponse.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates list failed: {exc}") from exc
        raise TemplatesClientError("unreachable")

    async def create_template(
        self,
        *,
        slug: str,
        title: str,
        category: str,
        description: str,
        filename: str,
        data: bytes,
    ) -> AdminTemplateOut:
        # Без ретрая: повтор удавшегося POST даст ложный 409 slug_taken.
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/admin/templates",
                    headers=self._headers(),
                    data={
                        "slug": slug,
                        "title": title,
                        "category": category,
                        "description": description,
                    },
                    files={"file": (filename, data, DOCX_CONTENT_TYPE)},
                )
                _raise_for_common(response)
                return AdminTemplateOut.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates create failed: {exc}") from exc

    async def patch_template(self, slug: str, payload: dict[str, Any]) -> AdminTemplateOut:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.patch(
                            f"{self._base_url}/admin/templates/{slug}",
                            json=payload,
                            headers=self._headers(),
                        )
                        _raise_for_common(response)
                        body = response.json()
                    return AdminTemplateOut.model_validate(body)
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates patch failed: {exc}") from exc
        raise TemplatesClientError("unreachable")

    async def replace_file(
        self, slug: str, *, filename: str, data: bytes
    ) -> TemplateFileReplaceResponse:
        # Без ретрая: повторять PUT файла вслепую не стоит.
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.put(
                    f"{self._base_url}/admin/templates/{slug}/file",
                    headers=self._headers(),
                    files={"file": (filename, data, DOCX_CONTENT_TYPE)},
                )
                _raise_for_common(response)
                return TemplateFileReplaceResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates replace failed: {exc}") from exc

    async def download_file(self, slug: str) -> bytes:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/admin/templates/{slug}/file",
                            headers=self._headers(),
                        )
                        _raise_for_common(response)
                        return response.content
        except httpx.HTTPError as exc:
            raise TemplatesClientError(f"templates download failed: {exc}") from exc
        raise TemplatesClientError("unreachable")

    async def delete_template(self, slug: str) -> None:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.delete(
                            f"{self._base_url}/admin/templates/{slug}",
                            headers=self._headers(),
                        )
                        _raise_for_common(response)
                        return
        except httpx.HTTPError as exc:
            raise TemplatesClientError(f"templates delete failed: {exc}") from exc
        raise TemplatesClientError("unreachable")
