"""Boundary: neurolegal.documents must not import neurolegal.agent / neurolegal.rag.

T-0103: скан на AST вместо строковых префиксов, см. tests/unit/importscan.py.
"""

from pathlib import Path

import neurolegal.documents
from tests.unit.importscan import format_offenders, scan_forbidden_imports

ROOT = Path(neurolegal.documents.__file__).parent


def test_documents_does_not_import_agent_or_rag() -> None:
    offenders = scan_forbidden_imports(
        ROOT,
        package="neurolegal.documents",
        forbidden=("neurolegal.agent", "neurolegal.rag", "neurolegal.templates"),
    )
    assert offenders == [], format_offenders("documents/ imports forbidden internals:", offenders)
