"""HTTP client for the templates service's public API (neurolegal-templates-api).

The agent talks to the templates service **only** through this client — never
by importing ``neurolegal.templates.*`` (boundary guard). Retries mirror the
RAG/documents clients' tenacity pattern; render ретраится тоже — подстановка
детерминированная, повтор безопасен.
"""

import httpx

from neurolegal.contracts import (
    RenderFieldError,
    RenderValidationError,
    TemplateDetail,
    TemplateListResponse,
    TemplateSummary,
)
from neurolegal.core.http import make_http_retry


class TemplatesClientError(RuntimeError):
    pass


class TemplatesNotFoundError(TemplatesClientError):
    """404 for a slug — unpublished или несуществующий; наружу неотличимо
    (спека §6: unpublish посреди диалога → честное сообщение)."""


class TemplateRenderInvalidError(TemplatesClientError):
    """422 рендера: структурные ошибки по полям — агент переспрашивает их."""

    def __init__(self, errors: list[RenderFieldError]) -> None:
        super().__init__("render validation failed")
        self.errors = errors


class AgentTemplatesClient:
    """Thin wrapper over the public ``/templates*`` API (:8003)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8003", timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def list_templates(self) -> list[TemplateSummary]:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(f"{self._base_url}/templates")
                        response.raise_for_status()
                        payload = response.json()
                    return TemplateListResponse.model_validate(payload).templates
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates list failed: {exc}") from exc
        raise TemplatesClientError("unreachable")

    async def get_template(self, slug: str) -> TemplateDetail:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(f"{self._base_url}/templates/{slug}")
                        if response.status_code == 404:
                            raise TemplatesNotFoundError(f"template not found: {slug}")
                        response.raise_for_status()
                        payload = response.json()
                    return TemplateDetail.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates get failed: {exc}") from exc
        raise TemplatesClientError("unreachable")

    async def render(self, slug: str, values: dict[str, str]) -> bytes:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.post(
                            f"{self._base_url}/templates/{slug}/render",
                            json={"values": values},
                        )
                        if response.status_code == 404:
                            raise TemplatesNotFoundError(f"template not found: {slug}")
                        if response.status_code == 422:
                            parsed = RenderValidationError.model_validate(response.json())
                            raise TemplateRenderInvalidError(parsed.errors)
                        response.raise_for_status()
                        return response.content
        except (httpx.HTTPError, ValueError) as exc:
            raise TemplatesClientError(f"templates render failed: {exc}") from exc
        raise TemplatesClientError("unreachable")
