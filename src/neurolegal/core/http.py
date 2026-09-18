"""Shared HTTP retry + OpenRouter constants for the network clients.

Both ``rag/`` and ``agent/`` reach OpenRouter / pravo.gov / the RAG service
over httpx with the same tenacity backoff (5 attempts, exponential jitter,
retry on transport/timeout errors). Keeping one factory here stops the retry
config and OpenRouter attribution headers from drifting across call sites.
"""

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_ATTRIBUTION_HEADERS = {
    "HTTP-Referer": "https://neurolegal.local",
    "X-Title": "Neurolegal",
}


def _is_retryable(exc: BaseException) -> bool:
    # 4xx responses are deterministic (bad key, validation error): retrying
    # them just stalls the caller through the full backoff schedule.
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    # TimeoutException and all transport errors are HTTPError subclasses.
    return isinstance(exc, httpx.HTTPError)


def _is_retryable_unsent(exc: BaseException) -> bool:
    """Retry only failures that prove the request never reached the server.

    A read timeout or a 5xx is ambiguous: the server may have already
    applied the request and lost the answer on the way back. Replaying a
    non-idempotent POST on those would create a second row — see
    ``DocumentsClient.upload``.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429  # rejected, never processed
    return isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | httpx.PoolTimeout)


def make_http_retry(*, idempotent: bool = True) -> AsyncRetrying:
    """Tenacity retry shared by the OpenRouter / pravo.gov / RAG HTTP clients.

    Retries transport/timeout errors, 5xx and 429; non-429 4xx fail fast.
    ``idempotent=False`` narrows this to connection-establishment failures
    and 429 — the cases where a replay cannot duplicate a side effect.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1.0, max=30.0),
        retry=retry_if_exception(_is_retryable if idempotent else _is_retryable_unsent),
        reraise=True,
    )
