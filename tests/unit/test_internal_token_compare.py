"""X-Internal-Token сверяется в постоянном времени (T-0101, пункт 7).

До этой задачи `grep compare_digest tests/` давал ноль: замена
`secrets.compare_digest` на обычное `!=` в обоих гейтах (агент и
сервис документов) не роняла ни одного теста, хотя это возвращает
тайминг-оракул на общий секрет — байт за байтом восстанавливаемый токен.

Поэтому здесь `secrets.compare_digest` подменяется шпионом: обычное
сравнение шпиона не вызовет, и мутация становится красной.
"""

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi import HTTPException

from neurolegal.agent.api.deps import verify_internal_token as agent_verify
from neurolegal.core.config import settings as core_settings
from neurolegal.documents.api.deps import verify_internal_token as hub_verify

Verify = Callable[..., Awaitable[None]]

_GATES = pytest.mark.parametrize("verify", [agent_verify, hub_verify], ids=["agent", "hub"])


@pytest.fixture
def digest_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    """Шпион вокруг secrets.compare_digest; отдаёт список пар аргументов."""
    calls: list[tuple[Any, Any]] = []
    real = secrets.compare_digest

    def spy(a: Any, b: Any) -> bool:
        calls.append((a, b))
        return bool(real(a, b))

    monkeypatch.setattr(secrets, "compare_digest", spy)
    return calls


@_GATES
async def test_matching_token_is_compared_in_constant_time(
    verify: Verify,
    digest_calls: list[tuple[Any, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_settings, "internal_token", "s3cret-token")
    await verify(x_internal_token="s3cret-token")  # проходит
    assert digest_calls == [("s3cret-token", "s3cret-token")]


@_GATES
async def test_wrong_token_is_401_and_still_constant_time(
    verify: Verify,
    digest_calls: list[tuple[Any, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_settings, "internal_token", "s3cret-token")
    with pytest.raises(HTTPException) as exc:
        await verify(x_internal_token="s3cret-tokeM")
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_internal_token"
    # Именно сверка секрета обязана идти через compare_digest — на ней
    # держится защита от побайтового подбора.
    assert digest_calls == [("s3cret-tokeM", "s3cret-token")]


@_GATES
async def test_absent_header_is_401_without_comparing(
    verify: Verify,
    digest_calls: list[tuple[Any, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_settings, "internal_token", "s3cret-token")
    with pytest.raises(HTTPException) as exc:
        await verify(x_internal_token=None)
    assert exc.value.status_code == 401
    assert digest_calls == []


@_GATES
async def test_unconfigured_token_is_a_noop(
    verify: Verify,
    digest_calls: list[tuple[Any, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Локальная разработка: секрет не задан — гейт пропускает всех."""
    monkeypatch.setattr(core_settings, "internal_token", None)
    await verify(x_internal_token="whatever")  # без исключения
    assert digest_calls == []
