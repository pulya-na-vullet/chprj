"""HTTP client from the RAG service to the agent's internal operator API.

The RAG admin surface talks to the agent **only** through this client —
never by importing ``neurolegal.agent.*`` modules directly. This is the first
(and so far deliberate, only) rag→agent HTTP link: the operator "Users" tab
lives in the RAG admin SPA, but `users`/`auth_sessions` are agent-owned
tables (design doc §1.7). Retries mirror `agent.tools.rag_client`'s tenacity
pattern.
"""

import httpx

from neurolegal.contracts import AdminUserOut, AdminUsersResponse
from neurolegal.core.http import make_http_retry


class AgentClientError(RuntimeError):
    pass


class AgentUserNotFoundError(AgentClientError):
    """The agent responded 404 for a specific user id — distinct from a
    generic outage so the proxy route can surface a 404 instead of a 502."""


class AgentAuthMisconfiguredError(AgentClientError):
    """The agent responded 401 — the agent<->hub internal token is missing or
    wrong on this service, not a generic agent outage. Distinct so the proxy
    route can tell an operator "fix your token" instead of "agent is down"."""


class AgentClient:
    """Thin wrapper over the agent's internal ``/admin/users*`` endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
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

    async def list_users(self) -> list[AdminUserOut]:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/admin/users", headers=self._headers()
                        )
                        if response.status_code == 401:
                            raise AgentAuthMisconfiguredError("agent rejected internal token")
                        response.raise_for_status()
                        payload = response.json()
                    return AdminUsersResponse.model_validate(payload).users
        except (httpx.HTTPError, ValueError) as exc:
            raise AgentClientError(f"agent list_users failed: {exc}") from exc
        raise AgentClientError("unreachable")

    async def patch_user(
        self, user_id: str, *, is_active: bool | None = None, new_password: str | None = None
    ) -> AdminUserOut:
        # PATCH semantics: send only the provided fields — the agent treats
        # an absent field as "leave unchanged".
        payload: dict[str, bool | str] = {}
        if is_active is not None:
            payload["is_active"] = is_active
        if new_password is not None:
            payload["new_password"] = new_password
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.patch(
                            f"{self._base_url}/admin/users/{user_id}",
                            json=payload,
                            headers=self._headers(),
                        )
                        if response.status_code == 404:
                            raise AgentUserNotFoundError(f"user not found: {user_id}")
                        if response.status_code == 401:
                            raise AgentAuthMisconfiguredError("agent rejected internal token")
                        response.raise_for_status()
                        body = response.json()
                    return AdminUserOut.model_validate(body)
        except (httpx.HTTPError, ValueError) as exc:
            raise AgentClientError(f"agent patch_user failed: {exc}") from exc
        raise AgentClientError("unreachable")
