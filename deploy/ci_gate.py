#!/usr/bin/env python3
"""Гейт выкатки: пускать ли этот тег на прод.

Запускается системным python3 на боевом хосте — до сборки образа и вне
контейнеров, поэтому только stdlib и никаких зависимостей проекта.

Зелёный прогон CI пушит метку `refs/ci-passed/<sha>` (см. .github/workflows/ci.yml).
Сервер читает её обычным git-fetch тем же read-only deploy key, поэтому схема
не требует ни одного нового секрета.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

MARKER_NAMESPACE = "refs/ci-passed"

# Причины отказа, по которым подбираются подсказки: для одной уместно
# рассказать про прогоны CI, для другой — только про обход. Для
# ненайденного тега обход бесполезен: тега от этого не появится.
NO_MARKER_REASON = "нет отметки CI на коммите тега"
OFF_MAIN_REASON = "коммит тега не принадлежит origin/main"

_REMOTE_RE = re.compile(
    r"^(?:git@github\.com:|https://github\.com/)(?P<slug>[^/]+/[^/]+?)(?:\.git)?$"
)


@dataclass(frozen=True)
class Verdict:
    """Решение гейта: код для журнала и причина для человека."""

    code: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.code != "blocked"


def decide(*, bypass: bool, is_rollback: bool, on_main: bool, marked: bool) -> Verdict:
    """Порядок проверок важен.

    Обход идёт первым: он обязан работать, когда сломано всё остальное.
    Откат — вторым: движение назад по истории (цель — предок работающей
    версии) не блокируется ничем, иначе гейт превращается в ловушку при
    сломанном проде. Проверяется именно родство коммитов, не факт прошлой
    выкатки: журнал выкаток гейту недоступен.
    """
    if bypass:
        return Verdict("bypassed", "ALLOW_UNVERIFIED=1 — проверки пропущены осознанно")
    if is_rollback:
        return Verdict("rollback", "откат: коммит тега — предок работающей версии")
    if not on_main:
        return Verdict("blocked", OFF_MAIN_REASON)
    if marked:
        return Verdict("passed", "CI на коммите тега зелёный")
    return Verdict("blocked", NO_MARKER_REASON)


def evaluate(
    *,
    tag: str,
    current_sha: str,
    main_ref: str,
    bypass: bool,
    resolve: Callable[[str], str | None],
    is_ancestor: Callable[[str, str], bool],
) -> Verdict:
    """Собрать факты про репозиторий и получить вердикт.

    Запросы к git передаются аргументами, чтобы композицию флагов можно было
    проверить тестами: ошибка здесь либо пропускает непроверенный код на прод,
    либо запирает откат.
    """
    target = resolve(tag)
    if target is None:
        return Verdict("blocked", f"тег {tag} не найден — сделан ли git push --tags?")

    current = resolve(current_sha)
    # Повторная выкатка того же коммита откатом не является: цель равна
    # работающей версии, и метка для неё обязательна на общих основаниях.
    rollback = current is not None and target != current and is_ancestor(target, current)
    return decide(
        bypass=bypass,
        is_rollback=rollback,
        on_main=is_ancestor(target, main_ref),
        marked=resolve(f"{MARKER_NAMESPACE}/{target}") is not None,
    )


def actions_url(remote: str) -> str | None:
    """Адрес прогонов CI по адресу origin. None, если origin ведёт не в github.com."""
    match = _REMOTE_RE.match(remote.strip())
    if match is None:
        return None
    return f"https://github.com/{match.group('slug')}/actions"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def _resolve(rev: str) -> str | None:
    """sha коммита за ссылкой или None, если ссылки нет."""
    found = _git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").stdout.strip()
    return found or None


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    return _git("merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def hint_lines(reason: str, tag: str, actions: str | None) -> list[str]:
    """Подсказки под причину отказа. Пустой список — причина говорит сама за себя."""
    if reason == NO_MARKER_REASON:
        return [
            f"Прогоны CI: {actions}" if actions else "Прогоны CI: см. GitHub Actions репозитория",
            f"Прогон ещё идёт — дождитесь зелёного и повторите: make deploy TAG={tag}",
            f"Прогона не было — запустите вручную: gh workflow run ci.yml --ref {tag}",
            f"Обход, только когда GitHub недоступен: ALLOW_UNVERIFIED=1 make deploy TAG={tag}",
        ]
    if reason == OFF_MAIN_REASON:
        return [f"Обход, только когда GitHub недоступен: ALLOW_UNVERIFIED=1 make deploy TAG={tag}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="гейт CI перед выкаткой")
    parser.add_argument("--tag", required=True, help="выкатываемый тег")
    parser.add_argument("--current-sha", required=True, help="коммит, работающий сейчас")
    parser.add_argument("--main-ref", default="origin/main", help="ссылка на основную ветку")
    args = parser.parse_args(argv)

    verdict = evaluate(
        tag=args.tag,
        current_sha=args.current_sha,
        main_ref=args.main_ref,
        bypass=os.environ.get("ALLOW_UNVERIFIED", "") not in ("", "0"),
        resolve=_resolve,
        is_ancestor=_is_ancestor,
    )

    print(verdict.code)
    if verdict.allowed:
        print(f"гейт: {verdict.reason}", file=sys.stderr)
        return 0
    print(f"ОТКАЗ: {verdict.reason}", file=sys.stderr)
    actions = actions_url(_git("remote", "get-url", "origin").stdout)
    for line in hint_lines(verdict.reason, args.tag, actions):
        print(line, file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
