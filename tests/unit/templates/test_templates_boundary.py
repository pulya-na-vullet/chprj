"""Boundary: neurolegal.templates imports only core/contracts — never
neurolegal.agent / neurolegal.rag / neurolegal.documents. Любые связи — только HTTP.

Скан на AST (T-0103), см. tests/unit/importscan.py.
"""

from pathlib import Path

import neurolegal.templates
from tests.unit.importscan import format_offenders, scan_forbidden_imports

ROOT = Path(neurolegal.templates.__file__).parent


def test_templates_does_not_import_agent_rag_or_documents() -> None:
    offenders = scan_forbidden_imports(
        ROOT,
        package="neurolegal.templates",
        forbidden=("neurolegal.agent", "neurolegal.rag", "neurolegal.documents"),
    )
    assert offenders == [], format_offenders("templates/ imports forbidden internals:", offenders)
