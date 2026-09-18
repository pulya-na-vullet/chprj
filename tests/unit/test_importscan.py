"""Негативный самотест детектора границ (T-0103, пункт 3).

Без него все три гарда зелены по построению: детектор, всегда возвращающий
пустой список, проходит их одинаково хорошо. Здесь на временном пакете
проверяется, что КАЖДАЯ известная форма обхода ловится, и что законные
импорты не помечаются.
"""

from pathlib import Path

from tests.unit.importscan import scan_forbidden_imports

FORBIDDEN = ("neurolegal.rag", "neurolegal.documents")

# По одному нарушению на строку — номера строк проверяются ниже.
_OFFENDING = '''\
"""Модуль-нарушитель."""

import neurolegal.rag
import neurolegal.rag.store.acts as acts_mod
from neurolegal.rag.store import acts
from neurolegal import rag
from ...documents.store import blob
import importlib

mod = importlib.import_module("neurolegal.rag.store.search")
other = __import__("neurolegal.documents.worker")
'''

_CLEAN = '''\
"""Законный модуль: HTTP-клиент и общий core."""

import neurolegal.core.db
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.core.config import settings
from ..llm.client import ChatLLM

# Строки, похожие на импорт, но импортом не являющиеся:
DOC = "neurolegal.rag.store"
IMPORTS = ["from neurolegal.rag import x"]
'''


def _make_pkg(tmp_path: Path, filename: str, source: str) -> Path:
    """`root/chat/<filename>` — вложенность нужна, чтобы `level=3` резолвился."""
    root = tmp_path / "agent"
    (root / "chat").mkdir(parents=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "chat" / "__init__.py").write_text("", encoding="utf-8")
    (root / "chat" / filename).write_text(source, encoding="utf-8")
    return root


def test_detector_catches_every_known_bypass(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path, "offender.py", _OFFENDING)

    found = scan_forbidden_imports(root, package="neurolegal.agent", forbidden=FORBIDDEN)
    names = {o.imported for o in found}

    assert "neurolegal.rag" in names  # import neurolegal.rag
    assert "neurolegal.rag.store.acts" in names  # import ... as
    assert "neurolegal.rag.store" in names  # from ... import (абсолютный)
    assert "neurolegal.rag.store.search" in names  # importlib.import_module(...)
    assert "neurolegal.documents.worker" in names  # __import__(...)
    # from neurolegal import rag — запрещённое имя приходит алиасом
    assert "neurolegal.rag" in names
    # from ...documents.store import blob — относительный импорт из
    # neurolegal.agent.chat: три точки уводят на neurolegal
    assert "neurolegal.documents.store" in names

    # Каждая строка-нарушитель отмечена, ни одна не потеряна.
    assert {o.line for o in found} == {3, 4, 5, 6, 7, 10, 11}


def test_detector_is_silent_on_legitimate_code(tmp_path: Path) -> None:
    root = _make_pkg(tmp_path, "clean.py", _CLEAN)
    assert scan_forbidden_imports(root, package="neurolegal.agent", forbidden=FORBIDDEN) == []


def test_relative_import_of_own_package_is_not_a_violation(tmp_path: Path) -> None:
    """`from .rag_client import X` внутри agent/ — законно и не должно ловиться,
    даже если в имени встречается слово rag."""
    root = _make_pkg(tmp_path, "own.py", "from .rag_client import RagClient\n")
    assert scan_forbidden_imports(root, package="neurolegal.agent", forbidden=FORBIDDEN) == []
