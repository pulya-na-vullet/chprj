"""Startup gate for the agent's internal /admin/users* router (T-0027).

The agent is public-facing, and these routes can reset any user's password /
deactivate any account. Their only auth is the X-Internal-Token, which is a
no-op when NEUROLEGAL_INTERNAL_TOKEN is unset. `_check_admin_users_gate` must:
- pass silently when a token is configured,
- fail fast when the operator required a token but didn't set one,
- warn (but not crash) when the routes are mounted open for local dev.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from neurolegal.agent.api.app import _check_admin_users_gate, _warn_if_multiworker, app
from neurolegal.core.config import settings


def test_gate_passes_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_token", "s3cret")
    monkeypatch.setattr(settings, "require_internal_token", True)
    _check_admin_users_gate()  # no raise


def test_gate_fails_fast_when_required_but_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_token", None)
    monkeypatch.setattr(settings, "require_internal_token", True)
    with pytest.raises(RuntimeError, match="NEUROLEGAL_REQUIRE_INTERNAL_TOKEN"):
        _check_admin_users_gate()


def test_gate_warns_but_allows_open_local_dev(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "internal_token", None)
    monkeypatch.setattr(settings, "require_internal_token", False)
    with caplog.at_level(logging.WARNING):
        _check_admin_users_gate()  # no raise
    assert any("/admin/users" in r.message for r in caplog.records)


def test_lifespan_actually_runs_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Проводка гейта, не сам гейт (T-0101, пункт 6).

    Функция выше покрыта тремя тестами, её ВЫЗОВ из lifespan — ничем:
    удаление строки `_check_admin_users_gate()` проходило весь набор, и
    агент при NEUROLEGAL_REQUIRE_INTERNAL_TOKEN=true поднимался бы
    вместо отказа на старте — на открытых внутренних ручках.
    """
    monkeypatch.setattr(settings, "internal_token", None)
    monkeypatch.setattr(settings, "require_internal_token", True)
    with pytest.raises(RuntimeError, match="NEUROLEGAL_REQUIRE_INTERNAL_TOKEN"), TestClient(app):
        pass  # pragma: no cover - старт обязан упасть


def test_lifespan_starts_when_token_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_token", "s3cret")
    monkeypatch.setattr(settings, "require_internal_token", True)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200


def test_multiworker_warning_fires_above_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with caplog.at_level(logging.WARNING):
        _warn_if_multiworker()
    assert any("WEB_CONCURRENCY" in r.message for r in caplog.records)


def test_multiworker_warning_silent_for_single_worker(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    with caplog.at_level(logging.WARNING):
        _warn_if_multiworker()
    assert not caplog.records
