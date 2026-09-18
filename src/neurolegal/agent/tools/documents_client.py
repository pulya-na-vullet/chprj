"""HTTP client for the documents hub (neurolegal-documents-api).

The agent talks to the hub **only** through this client — never by importing
``neurolegal.documents.*``. Retries mirror the RAG client's tenacity
pattern: the hub runs behind the same flaky network.
"""

from typing import cast

import httpx

from neurolegal.contracts import (
    HubDocumentContent,
    HubDocumentInfo,
    HubDocumentListResponse,
)
from neurolegal.core.http import make_http_retry


class DocumentsClientError(RuntimeError):
    pass


class DocumentsNotFoundError(DocumentsClientError):
    """The hub responded 404 for a specific document — distinct from a
    generic outage so callers can surface a 404 instead of a 502."""


class DocumentsClient:
    """Thin wrapper over the documents hub (``neurolegal.documents.api.app``)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8002",
        timeout: float = 30.0,
        internal_token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._internal_token = internal_token

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Every hub request carries X-Internal-Token when configured; callers
        merge in request-specific headers (X-User-Id) on top."""
        headers = dict(extra or {})
        if self._internal_token:
            headers["X-Internal-Token"] = self._internal_token
        return headers

    async def upload(
        self, data: bytes, filename: str, content_type: str, *, owner_id: str
    ) -> HubDocumentInfo:
        """Upload is the one non-idempotent call here: every POST creates a
        new document row. Retrying an ambiguous timeout would put a second
        copy in the user's library, so only unsent-request failures retry."""
        try:
            async for attempt in make_http_retry(idempotent=False):
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.post(
                            f"{self._base_url}/documents",
                            files={"file": (filename, data, content_type)},
                            headers=self._headers({"X-User-Id": owner_id}),
                        )
                        response.raise_for_status()
                        payload = response.json()
                    return HubDocumentInfo.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentsClientError(f"hub upload failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def get_info(self, document_id: str, user_id: str) -> HubDocumentInfo:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/documents/{document_id}",
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        if response.status_code == 404:
                            raise DocumentsNotFoundError(f"document not found: {document_id}")
                        response.raise_for_status()
                        payload = response.json()
                    return HubDocumentInfo.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentsClientError(f"hub get_info failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def get_content(self, document_id: str, user_id: str) -> HubDocumentContent:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/documents/{document_id}/content",
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        if response.status_code == 404:
                            raise DocumentsNotFoundError(f"document not found: {document_id}")
                        response.raise_for_status()
                        payload = response.json()
                    return HubDocumentContent.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentsClientError(f"hub get_content failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def list_for_conversation(
        self, conversation_id: str, user_id: str
    ) -> list[HubDocumentInfo]:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/conversations/{conversation_id}/documents",
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        response.raise_for_status()
                        payload = response.json()
                    return HubDocumentListResponse.model_validate(payload).documents
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentsClientError(f"hub list failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def list_for_owner(self, owner_id: str) -> list[HubDocumentInfo]:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/documents",
                            headers=self._headers({"X-User-Id": owner_id}),
                        )
                        response.raise_for_status()
                        payload = response.json()
                    return HubDocumentListResponse.model_validate(payload).documents
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentsClientError(f"hub list_for_owner failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def delete(self, document_id: str, user_id: str) -> None:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.delete(
                            f"{self._base_url}/documents/{document_id}",
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        if response.status_code == 404:
                            raise DocumentsNotFoundError(f"document not found: {document_id}")
                        response.raise_for_status()
                    return
        except httpx.HTTPError as exc:
            raise DocumentsClientError(f"hub delete failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def attach(self, document_id: str, conversation_id: str, user_id: str) -> HubDocumentInfo:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.post(
                            f"{self._base_url}/documents/{document_id}/attachments",
                            json={"conversation_id": conversation_id},
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        response.raise_for_status()
                        payload = response.json()
                    return HubDocumentInfo.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentsClientError(f"hub attach failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def detach(self, document_id: str, conversation_id: str, user_id: str) -> None:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.delete(
                            f"{self._base_url}/documents/{document_id}"
                            f"/attachments/{conversation_id}",
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        response.raise_for_status()
                    return
        except httpx.HTTPError as exc:
            raise DocumentsClientError(f"hub detach failed: {exc}") from exc
        raise DocumentsClientError("unreachable")

    async def download_location(self, document_id: str, user_id: str) -> str | None:
        """Return the presigned URL the hub redirects to, or None for 410
        (no stored original). Uses follow_redirects=False to read Location."""
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(
                        timeout=self._timeout, follow_redirects=False
                    ) as client:
                        response = await client.get(
                            f"{self._base_url}/documents/{document_id}/download",
                            headers=self._headers({"X-User-Id": user_id}),
                        )
                        if response.status_code == 404:
                            raise DocumentsNotFoundError(f"document not found: {document_id}")
                        if response.status_code == 410:
                            return None
                        if response.status_code in (301, 302, 303, 307, 308):
                            return cast(str | None, response.headers.get("location"))
                        response.raise_for_status()
                    return None
        except httpx.HTTPError as exc:
            raise DocumentsClientError(f"hub download failed: {exc}") from exc
        raise DocumentsClientError("unreachable")
