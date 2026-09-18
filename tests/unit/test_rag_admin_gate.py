"""NEUROLEGAL_ADMIN_ENABLED=False действительно снимает админ-поверхность
RAG-сервиса (T-0101, пункт 5).

Флаг проверялся только в рантайме дев-машины: ни один тест не убеждался,
что при выключенном флаге `/admin/*` и админская SPA не монтируются. Это
единственная защита прода — админка ходит без аутентификации и проксирует
управление пользователями агента (перечисление, смена пароля).

Флаг читается на уровне модуля `rag.api.app`, поэтому приложение при
выключенной админке приходится собрать отдельно. Модуль исполняется в
отдельный объект и не подставляется в `sys.modules`: глобальное состояние
процесса не меняется, порядок тестов ни на что не влияет (в наборе уже
есть order-dependent флаки — плодить новые нельзя).
"""

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import neurolegal.rag.api.app as rag_app_module
from neurolegal.core.config import settings

_APP_SOURCE = Path(str(rag_app_module.__file__))
_STATIC_DIR = _APP_SOURCE.parent / "static"


def _build_app(*, admin_enabled: bool, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Собрать свежий экземпляр приложения при заданном значении флага."""
    monkeypatch.setattr(settings, "admin_enabled", admin_enabled)
    spec = importlib.util.spec_from_file_location("_rag_app_probe", _APP_SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # намеренно мимо sys.modules
    built: FastAPI = module.app
    return built


def _paths(app: FastAPI) -> set[str]:
    return {str(getattr(route, "path", "")) for route in app.routes}


def test_admin_disabled_mounts_no_admin_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(admin_enabled=False, monkeypatch=monkeypatch)
    assert [p for p in _paths(app) if p.startswith("/admin")] == []


def test_admin_disabled_serves_404_for_admin_api_and_spa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(_build_app(admin_enabled=False, monkeypatch=monkeypatch))
    assert client.get("/admin/documents").status_code == 404
    assert client.get("/admin/users").status_code == 404
    assert client.get("/admin/indexes").status_code == 404
    # SPA админки тоже не монтируется — корень пуст.
    assert client.get("/").status_code == 404
    # Рабочие ручки сервиса при этом на месте. /metrics зовём по-настоящему,
    # /healthz — только проверяем, что смонтирован: внутри он делает SELECT 1,
    # тогда как юнит-тестам ходить в БД нельзя (T-0103).
    assert client.get("/metrics").status_code == 200
    assert {"/healthz", "/search", "/embed", "/acts"} <= _paths(client.app)  # type: ignore[arg-type]


def test_admin_enabled_mounts_admin_routes_and_spa(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(admin_enabled=True, monkeypatch=monkeypatch)
    paths = _paths(app)
    assert {"/admin/documents", "/admin/jobs", "/admin/indexes", "/admin/users"} <= paths
    # SPA монтируется на корень: путь Mount пустой, поэтому ищем по имени.
    names = {str(getattr(route, "name", "")) for route in app.routes}
    assert ("admin-ui" in names) is _STATIC_DIR.is_dir()
