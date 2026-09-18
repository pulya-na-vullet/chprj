"""Стартовые проверки сервиса документов подключены к lifespan (T-0101, пункт 6).

`check_tessdata` покрыта как функция, но её ВЫЗОВ из lifespan не был
покрыт ничем: удаление строки `check_tessdata(...)` проходило все тесты,
хотя в проде это возвращает поход liteparse в сеть за `rus.traineddata`
на первом же PDF (в air-gapped-деплое — отказ обработки).

Тест держит только отрицательную ветку: она падает раньше, чем lifespan
доберётся до БД, поэтому остаётся юнит-тестом без сети и без Postgres.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neurolegal.documents.api.app import app
from neurolegal.documents.config import settings
from neurolegal.documents.processing.preflight import PreflightError


def test_lifespan_preflights_tessdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "tessdata_path", tmp_path / "no-such-tessdata")
    with pytest.raises(PreflightError, match="OCR-данные не найдены"), TestClient(app):
        pass  # pragma: no cover - вход в lifespan обязан упасть
