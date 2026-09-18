"""Boundary check: agent/ must never import neurolegal.rag.* / neurolegal.documents.*.

Единственные законные пути наружу — HTTP-клиенты `agent.tools.rag_client` и
`agent.tools.documents_client`. Всё остальное под agent/ сканируется.

T-0103: скан переведён на разбор AST вместо строковых префиксов. Прежняя версия
пропускала относительный импорт, `from neurolegal import rag` и динамический
`importlib.import_module("neurolegal.rag...")` — три рабочих способа обойти
границу штатным синтаксисом. Сам детектор покрыт самотестом
(tests/unit/test_importscan.py).
"""

from pathlib import Path

import neurolegal.agent
from tests.unit.importscan import format_offenders, scan_forbidden_imports

AGENT_ROOT = Path(neurolegal.agent.__file__).parent


def test_agent_does_not_import_rag_internals() -> None:
    offenders = scan_forbidden_imports(
        AGENT_ROOT, package="neurolegal.agent", forbidden=("neurolegal.rag",)
    )
    assert offenders == [], format_offenders("agent/ imports rag internals:", offenders)


def test_agent_does_not_import_documents_hub_internals() -> None:
    offenders = scan_forbidden_imports(
        AGENT_ROOT, package="neurolegal.agent", forbidden=("neurolegal.documents",)
    )
    assert offenders == [], format_offenders("agent/ imports documents-hub internals:", offenders)


def test_agent_does_not_import_templates_internals() -> None:
    offenders = scan_forbidden_imports(
        AGENT_ROOT, package="neurolegal.agent", forbidden=("neurolegal.templates",)
    )
    assert offenders == [], format_offenders("agent/ imports templates internals:", offenders)
