"""AST-скан импортов для архитектурных гардов (T-0103, пункт 3).

Прежние гарды сравнивали строковые префиксы строк файла и обходились штатным
синтаксисом Python — проверено, все четыре формы проходили молча:

    from ...rag.store import acts          # относительный импорт
    from neurolegal import rag             # пакет как имя
    importlib.import_module("neurolegal.rag.store")
    __import__("neurolegal.rag")

Здесь разбор идёт по дереву: `ast.Import` / `ast.ImportFrom`, резолв
`level > 0` относительно пакета файла, плюс строковые литералы в
`importlib.import_module` / `__import__`. Сам детектор покрыт негативным
самотестом (tests/unit/test_importscan.py) — иначе он мог бы всегда
возвращать пустой список и все гарды были бы зелёными по построению.
"""

import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

_DYNAMIC_IMPORT_FUNCS = frozenset({"import_module", "__import__"})


@dataclass(frozen=True)
class Offender:
    path: str
    line: int
    imported: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.imported}"


def _package_of(py: Path, root: Path, package: str) -> str:
    """Пакет, относительно которого резолвятся точечные импорты файла.

    И для `pkg/sub/mod.py`, и для `pkg/sub/__init__.py` это `package.sub`.
    """
    rel = py.relative_to(root)
    return ".".join([package, *rel.parts[:-1]])


def _resolve_relative(pkg: str, level: int, module: str | None) -> str:
    """`from ...rag.store import x` внутри пакета → абсолютное имя модуля."""
    parts = pkg.split(".")
    if level > 1:
        parts = parts[: -(level - 1)]
    base = ".".join(parts)
    if not base:
        return module or ""
    return f"{base}.{module}" if module else base


def _matches(name: str, forbidden: Sequence[str]) -> bool:
    return any(name == f or name.startswith(f + ".") for f in forbidden)


def _imported_names(node: ast.AST, pkg: str) -> Iterable[str]:
    """Имена модулей, которые узел втягивает в файл."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name
        return
    if isinstance(node, ast.ImportFrom):
        base = (
            _resolve_relative(pkg, node.level, node.module) if node.level else (node.module or "")
        )
        if base:
            yield base
            # `from neurolegal import rag` — запрещённое имя приходит алиасом,
            # не модулем; без этой ветки форма проходит мимо гарда.
            for alias in node.names:
                yield f"{base}.{alias.name}"
        return
    if isinstance(node, ast.Call):
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name in _DYNAMIC_IMPORT_FUNCS and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                yield first.value


def scan_forbidden_imports(root: Path, *, package: str, forbidden: Sequence[str]) -> list[Offender]:
    """Найти в дереве `root` (пакет `package`) импорты запрещённых пакетов."""
    offenders: list[Offender] = []
    for py in sorted(root.rglob("*.py")):
        pkg = _package_of(py, root, package)
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            for name in _imported_names(node, pkg):
                if _matches(name, forbidden):
                    offenders.append(
                        Offender(str(py.relative_to(root)), getattr(node, "lineno", 0), name)
                    )
    return offenders


def format_offenders(title: str, offenders: Sequence[Offender]) -> str:
    return title + "\n" + "\n".join(str(o) for o in offenders)
