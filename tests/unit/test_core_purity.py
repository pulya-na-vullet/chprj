"""`core` — общий фундамент: ни HTTP-DTO, ни зависимостей от сервисов.

Первый тест исторический (после выделения contracts): если тип входит в тело
запроса или ответа, ему место в `neurolegal.contracts`.

Второй появился в T-0103. Гарда «core не импортирует rag/agent/documents» не
существовало вовсе — правило было записано в CLAUDE.md и держалось на
внимательности ревьюера. При этом нарушение обходится дороже прочих границ:
`core` импортируют все три сервиса, так что обратная стрелка мгновенно
превращается в цикл импорта.
"""

from pathlib import Path

import neurolegal.core
import neurolegal.core.domain as domain
from tests.unit.importscan import format_offenders, scan_forbidden_imports

CORE_ROOT = Path(neurolegal.core.__file__).parent


def test_core_domain_has_no_http_dtos() -> None:
    forbidden = {"SearchedArticle", "SearchedChunk", "SearchResponse"}
    leaked = forbidden & set(dir(domain))
    assert not leaked, f"HTTP DTOs leaked into core.domain: {sorted(leaked)}"


def test_core_does_not_import_services() -> None:
    offenders = scan_forbidden_imports(
        CORE_ROOT,
        package="neurolegal.core",
        forbidden=("neurolegal.rag", "neurolegal.agent", "neurolegal.documents"),
    )
    assert offenders == [], format_offenders("core/ imports service internals:", offenders)
