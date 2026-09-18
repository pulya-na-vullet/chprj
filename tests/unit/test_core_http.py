"""Retry-policy semantics of the shared HTTP retry factory.

Deterministic 4xx responses must fail fast; transport errors, 5xx and 429
keep the original retry-with-backoff behavior.
"""

import httpx
import pytest

from neurolegal.core.http import _is_retryable, make_http_retry


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://test/")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


@pytest.mark.parametrize("code", [400, 401, 404, 422])
def test_4xx_is_not_retryable(code: int) -> None:
    assert _is_retryable(_status_error(code)) is False


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_429_and_5xx_are_retryable(code: int) -> None:
    assert _is_retryable(_status_error(code)) is True


def test_transport_errors_are_retryable() -> None:
    assert _is_retryable(httpx.ConnectError("boom")) is True
    assert _is_retryable(httpx.ReadTimeout("slow")) is True


def test_non_httpx_errors_are_not_retryable() -> None:
    assert _is_retryable(ValueError("nope")) is False


@pytest.mark.asyncio
async def test_retry_loop_fails_fast_on_4xx() -> None:
    attempts = 0
    with pytest.raises(httpx.HTTPStatusError):
        async for attempt in make_http_retry():
            with attempt:
                attempts += 1
                raise _status_error(422)
    assert attempts == 1
