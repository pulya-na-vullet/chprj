"""Юнит-тесты не имеют права ходить в сеть (T-0103, пункт 1).

`tests/conftest.py` заливает `.env.local` в `os.environ`, поэтому в юнит-прогоне
виден настоящий `OPENROUTER_API_KEY` — и код, который спрашивает «ключ есть?»,
отвечает «да». Так `test_run_extraction_marks_ready` ходил на openrouter.ai:443
по-настоящему: зелёным он оставался только потому, что воркер глотает
исключение; платить за вызовы и ждать до пяти ретраев tenacity приходилось
на каждом прогоне.

Фикстура ниже перекрывает сам системный вызов подключения, поэтому ловит любой
путь наружу — httpx, requests, asyncpg, boto3, — не только тот, про который
мы уже знаем. Сообщение ошибки называет адрес: по нему сразу видно, какую
зависимость тест забыл подменить.
"""

import socket
from collections.abc import Iterator
from typing import Any

import pytest


class NetworkAccessError(RuntimeError):
    """Юнит-тест попытался открыть исходящее соединение."""


_HINT = (
    "Юнит-тесты работают без сети. Подмените клиент/флаг явно "
    "(monkeypatch на summarize/summary_enabled, фейковый httpx-транспорт и т.п.); "
    "тесты, которым сеть нужна по существу, живут в tests/integration."
)


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Рубит исходящие соединения на весь tests/unit.

    Перехватывается именно `connect`, не конструктор сокета: создание
    сокетов и `socketpair` внутри asyncio (self-pipe цикла событий) остаются
    рабочими, иначе половина асинхронных тестов не поднимется.
    """

    def _blocked(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        raise NetworkAccessError(f"попытка соединения с {address!r}. {_HINT}")

    def _blocked_create(address: Any, *args: Any, **kwargs: Any) -> Any:
        raise NetworkAccessError(f"попытка соединения с {address!r}. {_HINT}")

    monkeypatch.setattr(socket.socket, "connect", _blocked, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked, raising=True)
    monkeypatch.setattr(socket, "create_connection", _blocked_create, raising=True)
    yield
