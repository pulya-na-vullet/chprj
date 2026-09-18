"""Самотест блокировщика сети (T-0103, пункт 1).

Фикстура из tests/unit/conftest.py — гарант того, что юнит-прогон не ходит
наружу. Без этого теста она могла бы тихо перестать работать (переименовали
атрибут, сменилась версия socket-модуля), и весь набор снова начал бы платить
за вызовы OpenRouter, оставаясь зелёным.
"""

import socket

import pytest

from tests.unit.conftest import NetworkAccessError


def test_direct_socket_connect_is_blocked() -> None:
    with pytest.raises(NetworkAccessError, match="openrouter"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("openrouter.ai", 443))


def test_create_connection_is_blocked() -> None:
    with pytest.raises(NetworkAccessError):
        socket.create_connection(("127.0.0.1", 5432), timeout=0.1)


def test_httpx_request_is_blocked() -> None:
    """Через реальный HTTP-клиент — то есть на том самом пути, которым в сеть
    уходил воркер документов."""
    httpx = pytest.importorskip("httpx")
    with pytest.raises((NetworkAccessError, httpx.HTTPError)):
        httpx.get("https://openrouter.ai/api/v1/models", timeout=0.5)
