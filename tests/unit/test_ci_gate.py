"""Тесты гейта выкатки.

Модуль лежит около скрипта выкатки, отдельно от пакета: запускать
гейт будет системный python3 на боевом хосте до сборки образа. Поэтому
импорт идёт по пути файла.
"""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_GATE_PATH = Path(__file__).resolve().parents[2] / "deploy" / "ci_gate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_gate", _GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Регистрация до exec_module обязательна: dataclass при отложенных
    # аннотациях ищет свой модуль в sys.modules и падает, если там пусто.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ci_gate = _load()


def test_bypass_wins_over_everything() -> None:
    verdict = ci_gate.decide(bypass=True, is_rollback=False, on_main=False, marked=False)
    assert verdict.code == "bypassed"
    assert verdict.allowed


def test_rollback_allowed_without_marker() -> None:
    """Релиз, выпущенный до появления CI, обязан оставаться доступным для отката."""
    verdict = ci_gate.decide(bypass=False, is_rollback=True, on_main=True, marked=False)
    assert verdict.code == "rollback"
    assert verdict.allowed


def test_rollback_allowed_even_off_main() -> None:
    verdict = ci_gate.decide(bypass=False, is_rollback=True, on_main=False, marked=False)
    assert verdict.allowed


def test_marked_commit_on_main_passes() -> None:
    verdict = ci_gate.decide(bypass=False, is_rollback=False, on_main=True, marked=True)
    assert verdict.code == "passed"
    assert verdict.allowed


def test_unmarked_commit_is_blocked() -> None:
    verdict = ci_gate.decide(bypass=False, is_rollback=False, on_main=True, marked=False)
    assert verdict.code == "blocked"
    assert not verdict.allowed


def test_commit_outside_main_is_blocked_even_when_marked() -> None:
    verdict = ci_gate.decide(bypass=False, is_rollback=False, on_main=False, marked=True)
    assert verdict.code == "blocked"
    assert not verdict.allowed


TARGET = "a" * 40
CURRENT = "b" * 40
MARKER = f"refs/ci-passed/{TARGET}"


def _fakes(
    refs: dict[str, str], ancestors: set[tuple[str, str]]
) -> tuple[Callable[[str], str | None], Callable[[str, str], bool]]:
    """Пара git-запросов поверх словаря ссылок и множества отношений предок→потомок."""
    return refs.get, lambda ancestor, descendant: (ancestor, descendant) in ancestors


def _evaluate(
    refs: dict[str, str], ancestors: set[tuple[str, str]], *, bypass: bool = False
) -> object:
    resolve, is_ancestor = _fakes(refs, ancestors)
    return ci_gate.evaluate(
        tag="v1.0.0",
        current_sha="HEAD",
        main_ref="origin/main",
        bypass=bypass,
        resolve=resolve,
        is_ancestor=is_ancestor,
    )


def test_evaluate_blocks_unknown_tag() -> None:
    verdict = _evaluate({"HEAD": CURRENT}, set())
    assert verdict.code == "blocked"
    assert "v1.0.0" in verdict.reason


def test_evaluate_passes_marked_commit_on_main() -> None:
    verdict = _evaluate(
        {"v1.0.0": TARGET, "HEAD": CURRENT, MARKER: TARGET},
        {(TARGET, "origin/main")},
    )
    assert verdict.code == "passed"


def test_evaluate_blocks_marked_commit_outside_main() -> None:
    verdict = _evaluate({"v1.0.0": TARGET, "HEAD": CURRENT, MARKER: TARGET}, set())
    assert verdict.code == "blocked"


def test_evaluate_blocks_unmarked_commit_on_main() -> None:
    verdict = _evaluate({"v1.0.0": TARGET, "HEAD": CURRENT}, {(TARGET, "origin/main")})
    assert verdict.code == "blocked"
    assert not verdict.allowed


def test_evaluate_calls_rollback_when_target_precedes_current() -> None:
    """Метки нет, зато цель — предок работающей версии: откат обязан пройти."""
    verdict = _evaluate({"v1.0.0": TARGET, "HEAD": CURRENT}, {(TARGET, CURRENT)})
    assert verdict.code == "rollback"
    assert verdict.allowed


def test_evaluate_does_not_treat_redeploy_as_rollback() -> None:
    """Тот же коммит, что работает сейчас: метка нужна на общих основаниях."""
    verdict = _evaluate(
        {"v1.0.0": TARGET, "HEAD": TARGET},
        {(TARGET, TARGET), (TARGET, "origin/main")},
    )
    assert verdict.code == "blocked"


def test_evaluate_redeploy_of_marked_commit_passes() -> None:
    verdict = _evaluate(
        {"v1.0.0": TARGET, "HEAD": TARGET, MARKER: TARGET},
        {(TARGET, TARGET), (TARGET, "origin/main")},
    )
    assert verdict.code == "passed"


def test_evaluate_bypass_skips_every_git_fact() -> None:
    verdict = _evaluate({"v1.0.0": TARGET, "HEAD": CURRENT}, set(), bypass=True)
    assert verdict.code == "bypassed"


def test_evaluate_looks_for_marker_under_target_sha() -> None:
    asked: list[str] = []

    def resolve(ref: str) -> str | None:
        asked.append(ref)
        return {"v1.0.0": TARGET, "HEAD": CURRENT}.get(ref)

    ci_gate.evaluate(
        tag="v1.0.0",
        current_sha="HEAD",
        main_ref="origin/main",
        bypass=False,
        resolve=resolve,
        is_ancestor=lambda a, d: d == "origin/main",
    )
    assert MARKER in asked


def test_hints_for_missing_marker_point_at_runs_and_bypass() -> None:
    lines = ci_gate.hint_lines(ci_gate.NO_MARKER_REASON, "v1.0.0", "https://example.test/actions")
    assert any("https://example.test/actions" in line for line in lines)
    assert any("ALLOW_UNVERIFIED=1" in line for line in lines)


def test_hints_for_commit_outside_main_offer_only_bypass() -> None:
    lines = ci_gate.hint_lines(ci_gate.OFF_MAIN_REASON, "v1.0.0", "https://example.test/actions")
    assert lines == [
        "Обход, только когда GitHub недоступен: ALLOW_UNVERIFIED=1 make deploy TAG=v1.0.0"
    ]


def test_no_hints_for_missing_tag() -> None:
    """Обход не создаст пропавшую ссылку, поэтому предлагать обход незачем."""
    assert ci_gate.hint_lines("тег v1.0.0 не найден", "v1.0.0", None) == []


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:owner/repo.git", "https://github.com/owner/repo/actions"),
        ("https://github.com/owner/repo.git", "https://github.com/owner/repo/actions"),
        ("https://github.com/owner/repo", "https://github.com/owner/repo/actions"),
        ("  git@github.com:owner/repo.git\n", "https://github.com/owner/repo/actions"),
    ],
)
def test_actions_url_from_remote(remote: str, expected: str) -> None:
    assert ci_gate.actions_url(remote) == expected


def test_actions_url_unparsable_returns_none() -> None:
    assert ci_gate.actions_url("/srv/local/mirror.git") is None
