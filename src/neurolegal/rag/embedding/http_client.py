"""HTTP client embedder — used by retrieval when /embed is split into a
separate microservice. Calls our own POST /embed contract (not OpenAI-shaped)."""

import httpx


class HttpEmbedder:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/embed",
                json={"texts": texts},
            )
            response.raise_for_status()
            return list(response.json()["vectors"])
