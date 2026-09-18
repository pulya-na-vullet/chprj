"""Fail-fast гейт internal token на старте templates-сервиса (T-0139, спека §9).

Семантика сервиса документов повторена: требование без значения — падение,
открытый локальный дефолт — предупреждаемо допустим. Проводка через lifespan
проверяется реальным стартом ASGI-приложения (TestClient поднимает lifespan).
"""

import pytest
from fastapi.testclient import TestClient

from neurolegal.core.config import settings as core_settings
from neurolegal.templates.api.app import app, check_internal_token


def test_gate_passes_with_token() -> None:
    check_internal_token(True, "s3cret")  # no raise


def test_gate_fails_fast_when_required_but_unset() -> None:
    with pytest.raises(RuntimeError, match="NEUROLEGAL_REQUIRE_INTERNAL_TOKEN"):
        check_internal_token(True, None)


def test_gate_allows_open_local_dev() -> None:
    check_internal_token(False, None)  # no raise


def test_lifespan_actually_runs_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проводка гейта, не сам гейт: удаление вызова из lifespan обязано
    ронять этот тест — иначе сервис при required-токене без значения тихо
    поднимется, оставив операторские ручки открытыми."""
    monkeypatch.setattr(core_settings, "require_internal_token", True)
    monkeypatch.setattr(core_settings, "internal_token", None)
    with (
        pytest.raises(RuntimeError, match="NEUROLEGAL_REQUIRE_INTERNAL_TOKEN"),
        TestClient(app),
    ):
        pass
