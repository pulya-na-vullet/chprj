"""Boundary check: rag/ must never import neurolegal.agent.* directly.

T-0022 ввела единственную (и намеренно единственную) связь rag→agent —
операторскую вкладку «Пользователи», — но она HTTP-only, через
`neurolegal.rag.agent_client`. Всё остальное под rag/ сканируется.

T-0103: скан на AST вместо строковых префиксов, см. tests/unit/importscan.py.
"""

from pathlib import Path

import neurolegal.rag
from tests.unit.importscan import format_offenders, scan_forbidden_imports

RAG_ROOT = Path(neurolegal.rag.__file__).parent


def test_rag_does_not_import_agent_internals() -> None:
    offenders = scan_forbidden_imports(
        RAG_ROOT, package="neurolegal.rag", forbidden=("neurolegal.agent",)
    )
    assert offenders == [], format_offenders("rag/ imports agent internals:", offenders)


def test_rag_does_not_import_templates_internals() -> None:
    offenders = scan_forbidden_imports(
        RAG_ROOT, package="neurolegal.rag", forbidden=("neurolegal.templates",)
    )
    assert offenders == [], format_offenders("rag/ imports templates internals:", offenders)
