# P0: Documents Upload + Contract Risk Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Юрист загружает договор (DOCX/PDF) в чат, задаёт по нему вопросы и запускает проверку рисков по YAML-плейбуку; отчёт (риски с цитатами договора и нормами + карта покрытия) приходит как сообщение беседы.

**Architecture:** Новый agent-owned модуль `src/neurolegal/agent/review/` (парсер → дерево секций → плейбук-движок из 5 стадий), таблица `documents` + JSON-колонка `messages.review`, команда `risk_review` внутри существующего SSE-хода `POST /chat`, два новых SSE-события. Граундинг только через существующий `RagClient` (HTTP). Фронт: скрепка в композере, карточки документов, чек-лист прогресса, рендер отчёта.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / python-docx / liteparse / pytest; React + Vite + TS.

Spec: `product/specs/2026-07-05-p0-contract-review-design.md`.

## Global Constraints

- Запуск инструментов только через uv: `uv run pytest…`, `uv run mypy src`, `uv run ruff check`.
- mypy strict обязан проходить; pre-commit хук гоняет ruff+mypy на каждый коммит.
- Коммиты: `type(scope): subject`, БЕЗ `Co-Authored-By`.
- `agent/` НЕ импортирует `neurolegal.rag.*` (тест `tests/unit/test_agent_boundary.py` уронит сборку). RAG — только через `neurolegal.agent.tools.rag_client.RagClient`.
- Все HTTP DTO — в `src/neurolegal/contracts/`; менять API ⇒ регенерить OpenAPI-снапшоты (`uv run python -m scripts.generate_openapi`, `npm --prefix frontend run openapi:generate`) и коммитить вместе (`tests/unit/test_contracts_openapi.py` — гейт).
- Юнит-тесты без сети/БД (SQLite in-memory для стора — паттерн см. существующие тесты стора).
- Перед коммитом фронтовых изменений: `npm --prefix frontend run build` (бандл `src/neurolegal/agent/api/static/` коммитится).
- UI: язык Alfa Kurs — монохром + красный `--accent`, без кричащих плашек; токены в `frontend/src/styles/tokens.css`.
- Лимит сообщения в чате: `MAX_MESSAGE_CHARS` = 2000 (см. `contracts/chat.py`) — не менять.

---

### Task 1: Зависимости и конфиг

**Files:**
- Modify: `pyproject.toml` (deps)
- Modify: `src/neurolegal/core/config.py`
- Test: `tests/unit/test_config.py` (если есть — дополнить; иначе создать)

**Interfaces:**
- Produces: `settings.playbooks_dir: Path` (env `NEUROLEGAL_PLAYBOOKS_DIR`, default `Path("playbooks")`), `settings.review_model: str | None` (env `NEUROLEGAL_REVIEW_MODEL`, default `None`).

- [ ] **Step 1: Добавить зависимости**

```bash
uv add liteparse
```

(python-docx уже в deps.) Проверить: `uv run python -c "import liteparse; print(liteparse.__version__)"` → `2.4.x`.

- [ ] **Step 2: Изучить фактический API liteparse**

Run: `uv run python -c "from liteparse import LiteParse; help(LiteParse.parse)" | head -40`
Зафиксировать: имя kwarg для языка OCR (ожидается `ocr_language="rus"` или аналог) и поле результата с текстом (`result.text` / markdown). Использовать фактические имена в Task 4.

- [ ] **Step 3: Расширить Settings**

В `src/neurolegal/core/config.py` в класс настроек (поля с env-префиксом по образцу соседних, например `rag_base_url`):

```python
playbooks_dir: Path = Path("playbooks")
review_model: str | None = None
```

с env-алиасами `NEUROLEGAL_PLAYBOOKS_DIR`, `NEUROLEGAL_REVIEW_MODEL` (точно в стиле существующих полей файла — посмотреть, как объявлен `rag_base_url`, повторить).

- [ ] **Step 4: Тест значений по умолчанию**

```python
def test_playbooks_settings_defaults() -> None:
    from neurolegal.core.config import Settings
    s = Settings(_env_file=None)
    assert s.playbooks_dir == Path("playbooks")
    assert s.review_model is None
```

Run: `uv run pytest tests/unit/test_config.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/neurolegal/core/config.py tests/unit/test_config.py
git commit -m "feat(review): liteparse dep + playbooks/review settings"
```

---

### Task 2: Плейбук — модели, загрузчик, первый YAML (услуги)

**Files:**
- Create: `src/neurolegal/agent/review/__init__.py` (пустой)
- Create: `src/neurolegal/agent/review/playbook.py`
- Create: `playbooks/services_ru.yaml`
- Test: `tests/unit/test_review_playbook.py`

**Interfaces:**
- Produces:
  - `PlaybookRule(BaseModel)`: `id: str`, `title: str`, `question: str`, `anchors: list[str] = []`, `risk_if_missing: Literal["high","medium","low"] | None = None`, `law_hints: list[str] = []`, `rag_queries: list[str] = []`
  - `Playbook(BaseModel)`: `id: str`, `name: str`, `rules: list[PlaybookRule]` (валидатор: ≥1 правило, id правил уникальны)
  - `load_playbooks(directory: Path) -> dict[str, Playbook]` — читает все `*.yaml`, ключ — `Playbook.id`; кидает `PlaybookError` на дубли id плейбуков/правил и невалидный YAML.
  - `class PlaybookError(Exception)`

- [ ] **Step 1: Failing test**

```python
from pathlib import Path

import pytest

from neurolegal.agent.review.playbook import Playbook, PlaybookError, load_playbooks

MINIMAL = """
id: test_pb
name: Тестовый
rules:
  - id: r1
    title: Оплата
    question: Определён ли срок оплаты?
    risk_if_missing: high
    rag_queries: ["срок оплаты"]
"""


def test_load_playbooks_parses_yaml(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(MINIMAL, encoding="utf-8")
    pbs = load_playbooks(tmp_path)
    assert set(pbs) == {"test_pb"}
    assert pbs["test_pb"].rules[0].risk_if_missing == "high"
    assert pbs["test_pb"].rules[0].anchors == []


def test_duplicate_rule_ids_rejected(tmp_path: Path) -> None:
    bad = MINIMAL + "  - id: r1\n    title: Дубль\n    question: q\n"
    (tmp_path / "a.yaml").write_text(bad, encoding="utf-8")
    with pytest.raises(PlaybookError):
        load_playbooks(tmp_path)


def test_shipped_playbooks_are_valid() -> None:
    pbs = load_playbooks(Path("playbooks"))
    assert "services_ru" in pbs
    for pb in pbs.values():
        assert 10 <= len(pb.rules) <= 30
```

Run: `uv run pytest tests/unit/test_review_playbook.py -q` → FAIL (module not found).

- [ ] **Step 2: Реализация playbook.py**

```python
"""Плейбук проверки договора: Pydantic-модели и загрузчик YAML."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class PlaybookError(Exception):
    pass


class PlaybookRule(BaseModel):
    id: str
    title: str
    question: str
    anchors: list[str] = Field(default_factory=list)
    risk_if_missing: Literal["high", "medium", "low"] | None = None
    law_hints: list[str] = Field(default_factory=list)
    rag_queries: list[str] = Field(default_factory=list)


class Playbook(BaseModel):
    id: str
    name: str
    rules: list[PlaybookRule] = Field(min_length=1)

    @field_validator("rules")
    @classmethod
    def _unique_rule_ids(cls, v: list[PlaybookRule]) -> list[PlaybookRule]:
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rule ids")
        return v


def load_playbooks(directory: Path) -> dict[str, Playbook]:
    result: dict[str, Playbook] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            pb = Playbook.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise PlaybookError(f"{path.name}: {exc}") from exc
        if pb.id in result:
            raise PlaybookError(f"duplicate playbook id: {pb.id}")
        result[pb.id] = pb
    return result
```

- [ ] **Step 3: Написать `playbooks/services_ru.yaml` — полный плейбук услуг (15 правил)**

```yaml
id: services_ru
name: Возмездное оказание услуг
rules:
  - id: subject
    title: Предмет договора
    question: >
      Определён ли предмет: какие именно услуги, в каком объёме и в какие
      сроки оказываются? Есть ли отсылка к приложению/ТЗ и приложено ли оно?
    anchors: ["предмет", "услуг"]
    risk_if_missing: high
    law_hints: ["ст. 779 ГК РФ", "ст. 432 ГК РФ"]
    rag_queries: ["предмет договора возмездного оказания услуг существенные условия"]
  - id: payment_terms
    title: Цена и порядок оплаты
    question: >
      Определены ли цена, срок и порядок оплаты? Нет ли условий, ставящих
      оплату в зависимость от действий третьих лиц или событий, которыми
      управляет заказчик?
    anchors: ["оплат", "цена", "стоимост", "расчет"]
    risk_if_missing: high
    law_hints: ["ст. 781 ГК РФ"]
    rag_queries: ["оплата услуг срок порядок возмездное оказание"]
  - id: acceptance
    title: Приёмка услуг
    question: >
      Установлен ли порядок сдачи-приёмки (акт, срок на мотивированный отказ)?
      Есть ли условие о молчаливой приёмке и в чью пользу оно работает?
    anchors: ["приемк", "акт", "сдач"]
    risk_if_missing: medium
    law_hints: ["ст. 783 ГК РФ", "ст. 720 ГК РФ"]
    rag_queries: ["приемка услуг акт мотивированный отказ"]
  - id: unilateral_termination
    title: Односторонний отказ
    question: >
      Как урегулирован односторонний отказ каждой из сторон? Ограничен ли
      законный отказ заказчика (ст. 782 ГК) неустойкой или запретом —
      такие ограничения ничтожны/оспоримы.
    anchors: ["отказ", "расторж"]
    risk_if_missing: medium
    law_hints: ["ст. 782 ГК РФ", "ст. 310 ГК РФ"]
    rag_queries: ["односторонний отказ от договора возмездного оказания услуг"]
  - id: liability_cap
    title: Ответственность и её пределы
    question: >
      Сбалансирована ли ответственность сторон? Нет ли одностороннего
      ограничения (только у исполнителя/только у заказчика), исключения
      ответственности за умысел (ничтожно) или неограниченной неустойки?
    anchors: ["ответственност", "неустойк", "пени", "штраф"]
    risk_if_missing: medium
    law_hints: ["ст. 401 ГК РФ", "ст. 330 ГК РФ", "ст. 333 ГК РФ"]
    rag_queries: ["ограничение ответственности по договору неустойка"]
  - id: deadlines
    title: Сроки оказания услуг
    question: >
      Определены ли начальный и конечный сроки? Привязаны ли сроки к событиям,
      которые могут не наступить (оплата аванса и т.п.), без правил ст. 314 ГК?
    anchors: ["срок"]
    risk_if_missing: high
    law_hints: ["ст. 708 ГК РФ", "ст. 314 ГК РФ"]
    rag_queries: ["срок оказания услуг начальный конечный"]
  - id: ip_rights
    title: Права на результаты
    question: >
      Если услуги создают результаты интеллектуальной деятельности —
      урегулирован ли переход исключительных прав, момент перехода и цена?
    anchors: ["интеллектуальн", "исключительн", "права на результ"]
    law_hints: ["ст. 1288 ГК РФ", "ст. 1296 ГК РФ"]
    rag_queries: ["исключительные права на результат работ по договору"]
  - id: confidentiality
    title: Конфиденциальность
    question: >
      Есть ли режим конфиденциальности: что признаётся конфиденциальной
      информацией, срок действия, ответственность за разглашение?
    anchors: ["конфиденциальн", "тайн"]
    law_hints: ["ст. 434.1 ГК РФ"]
    rag_queries: ["конфиденциальность коммерческая тайна договор"]
  - id: personal_data
    title: Персональные данные
    question: >
      Если исполнитель получает доступ к персональным данным — есть ли
      поручение на обработку с обязательными условиями 152-ФЗ?
    anchors: ["персональн"]
    law_hints: ["ст. 6 152-ФЗ"]
    rag_queries: ["поручение обработки персональных данных оператор"]
  - id: subcontractors
    title: Привлечение третьих лиц
    question: >
      Может ли исполнитель привлекать субисполнителей? По умолчанию услуги
      оказываются лично (ст. 780 ГК) — соответствует ли текст ожиданиям сторон?
    anchors: ["третьих лиц", "субисполнит", "лично"]
    law_hints: ["ст. 780 ГК РФ"]
    rag_queries: ["личное оказание услуг привлечение третьих лиц"]
  - id: force_majeure
    title: Форс-мажор
    question: >
      Не расширен ли форс-мажор до обычных предпринимательских рисков
      (изменение курса, действия контрагентов)? Есть ли порядок уведомления?
    anchors: ["непреодолим", "форс-мажор"]
    law_hints: ["ст. 401 ГК РФ"]
    rag_queries: ["непреодолимая сила предпринимательский риск"]
  - id: disputes
    title: Претензии и подсудность
    question: >
      Установлен ли претензионный порядок и срок ответа? Подсудность —
      не создаёт ли неудобный форум? Для арбитража претензионный порядок
      обязателен по АПК.
    anchors: ["претензи", "подсудност", "арбитраж", "спор"]
    risk_if_missing: low
    law_hints: ["ст. 4 АПК РФ"]
    rag_queries: ["претензионный порядок арбитражный суд обязательный"]
  - id: term_validity
    title: Срок действия договора
    question: >
      Определён ли срок действия и что происходит по его истечении
      (пролонгация, прекращение обязательств)? Распространяется ли договор
      на отношения до подписания?
    anchors: ["срок действия", "пролонг"]
    risk_if_missing: low
    law_hints: ["ст. 425 ГК РФ"]
    rag_queries: ["срок действия договора пролонгация"]
  - id: change_conditions
    title: Изменение условий
    question: >
      Может ли одна сторона менять условия (цену, объём) в одностороннем
      порядке? Для не-предпринимателей такое условие недействительно.
    anchors: ["одностороннем порядке", "изменени"]
    law_hints: ["ст. 310 ГК РФ", "ст. 450 ГК РФ"]
    rag_queries: ["одностороннее изменение условий договора"]
  - id: requisites_signatures
    title: Реквизиты и полномочия
    question: >
      Есть ли полные реквизиты сторон? Указано ли основание полномочий
      подписанта (устав, доверенность с датой/номером)?
    anchors: ["реквизит", "доверенност", "устав"]
    risk_if_missing: medium
    law_hints: ["ст. 53 ГК РФ", "ст. 183 ГК РФ"]
    rag_queries: ["полномочия подписанта договор доверенность"]
```

- [ ] **Step 4: Прогнать тесты**

Run: `uv run pytest tests/unit/test_review_playbook.py -q` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/neurolegal/agent/review/ playbooks/ tests/unit/test_review_playbook.py
git commit -m "feat(review): playbook models, YAML loader, services_ru playbook"
```

---

### Task 3: Дерево секций договора

**Files:**
- Create: `src/neurolegal/agent/review/sections.py`
- Test: `tests/unit/test_review_sections.py`

**Interfaces:**
- Produces:
  - `@dataclass DocSection`: `number: str` («1», «1.2», «preamble», «trailing», «p1»…), `title: str | None`, `text: str` (весь текст секции, включая заголовок), `level: int` (кол-во точек+1; 0 для spec-секций), `start: int`, `end: int` (char-offsets в full_text)
  - `build_sections(paragraphs: list[str]) -> tuple[list[DocSection], str]` — вторым элементом возвращает `full_text` (абзацы через `"\n"`), offsets секций указывают в него.
- Правила: абзац, матчащий `^(\d+(?:\.\d+)*(?:-\d+)?)[.)]\s+` — начало секции (number = группа 1, title = остаток строки до 80 симв.). Абзацы до первой нумерованной — секция `preamble`. Абзац, матчащий `(?i)^(адреса|реквизиты|подписи)\b` — начало секции `trailing`. Ненумерованные абзацы приклеиваются к текущей секции. Если нумерованных нет вообще — деградация: секции `p1`, `p2`… по группам подряд идущих абзацев ≤ 1500 симв.

- [ ] **Step 1: Failing tests**

```python
from neurolegal.agent.review.sections import build_sections

NUMBERED = [
    "ДОГОВОР оказания услуг № 1",
    "1. Предмет договора",
    "1.1. Исполнитель обязуется оказать услуги.",
    "2. Оплата",
    "Оплата в течение 10 дней.",
    "Реквизиты и подписи сторон",
    "ООО Ромашка",
]


def test_numbered_document_sections() -> None:
    sections, full_text = build_sections(NUMBERED)
    numbers = [s.number for s in sections]
    assert numbers == ["preamble", "1", "1.1", "2", "trailing"]
    s2 = next(s for s in sections if s.number == "2")
    assert "10 дней" in s2.text
    assert full_text[s2.start : s2.end] == s2.text
    assert next(s for s in sections if s.number == "1.1").level == 2


def test_suffix_numbering() -> None:
    sections, _ = build_sections(["1. А", "1.1-1. Б вставная"])
    assert [s.number for s in sections] == ["1", "1.1-1"]


def test_plain_document_degrades_to_chunks() -> None:
    paras = ["строка " + "х" * 400] * 10  # без нумерации
    sections, _ = build_sections(paras)
    assert all(s.number.startswith("p") for s in sections)
    assert all(len(s.text) <= 1600 for s in sections)
    assert len(sections) >= 2
```

Run: `uv run pytest tests/unit/test_review_sections.py -q` → FAIL.

- [ ] **Step 2: Реализация**

```python
"""Построение дерева секций договора из плоского списка абзацев."""

import re
from dataclasses import dataclass

_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*(?:-\d+)?)[.)]\s+(.*)")
_TRAILING_RE = re.compile(r"(?i)^(адреса|реквизиты|подписи)\b")
_CHUNK_LIMIT = 1500


@dataclass
class DocSection:
    number: str
    title: str | None
    text: str
    level: int
    start: int
    end: int


def build_sections(paragraphs: list[str]) -> tuple[list[DocSection], str]:
    paras = [p.strip() for p in paragraphs if p.strip()]
    full_text = "\n".join(paras)
    if not any(_NUM_RE.match(p) for p in paras):
        return _chunked(paras, full_text), full_text

    sections: list[DocSection] = []
    current_number, current_title, current_level = "preamble", None, 0
    buf: list[str] = []
    offset = 0

    def flush() -> None:
        nonlocal offset
        if not buf:
            return
        text = "\n".join(buf)
        start = full_text.index(text, offset)
        sections.append(
            DocSection(current_number, current_title, text, current_level, start, start + len(text))
        )
        offset = start + len(text)
        buf.clear()

    for p in paras:
        m = _NUM_RE.match(p)
        if m:
            flush()
            current_number = m.group(1)
            current_title = m.group(2)[:80] or None
            current_level = current_number.count(".") + 1
        elif _TRAILING_RE.match(p):
            flush()
            current_number, current_title, current_level = "trailing", p[:80], 0
        buf.append(p)
    flush()
    return sections, full_text


def _chunked(paras: list[str], full_text: str) -> list[DocSection]:
    sections: list[DocSection] = []
    buf: list[str] = []
    size = 0
    offset = 0

    def flush() -> None:
        nonlocal offset, size
        if not buf:
            return
        text = "\n".join(buf)
        start = full_text.index(text, offset)
        sections.append(
            DocSection(f"p{len(sections) + 1}", None, text, 0, start, start + len(text))
        )
        offset = start + len(text)
        buf.clear()
        size = 0

    for p in paras:
        if size + len(p) > _CHUNK_LIMIT:
            flush()
        buf.append(p)
        size += len(p)
    flush()
    return sections
```

- [ ] **Step 3: Тесты зелёные**

Run: `uv run pytest tests/unit/test_review_sections.py -q` → 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/agent/review/sections.py tests/unit/test_review_sections.py
git commit -m "feat(review): contract section tree builder with offsets"
```

---

### Task 4: Парсеры DOCX/PDF

**Files:**
- Create: `src/neurolegal/agent/review/parser.py`
- Create: `tests/data/contracts/services_minimal.docx` (сгенерить python-docx-скриптом в тесте-фикстуре, НЕ бинарь в гите — см. Step 1)
- Test: `tests/unit/test_review_parser.py`

**Interfaces:**
- Produces:
  - `@dataclass ParsedContract`: `sections: list[DocSection]`, `full_text: str`, `parser: str` (`"docx"` | `"pdf"`)
  - `class ContractParseError(Exception)` — человекочитаемое сообщение (показывается в UI).
  - `parse_contract(data: bytes, filename: str) -> ParsedContract` — диспетчер по расширению; неизвестное расширение → `ContractParseError`.
- PDF: liteparse; текст → `splitlines()` → `build_sections`. OCR-язык rus (фактический kwarg из Task 1 Step 2). Ошибка liteparse (вкл. отсутствие Tesseract для скана) → `ContractParseError("Не удалось извлечь текст из PDF: …")`.

- [ ] **Step 1: Failing tests (DOCX-фикстура строится в tmp_path)**

```python
import io
from pathlib import Path

import pytest
from docx import Document

from neurolegal.agent.review.parser import ContractParseError, parse_contract


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_parse_docx_builds_sections() -> None:
    data = _docx_bytes(["Договор", "1. Предмет", "Текст предмета.", "2. Оплата", "10 дней."])
    parsed = parse_contract(data, "договор.docx")
    assert parsed.parser == "docx"
    assert [s.number for s in parsed.sections] == ["preamble", "1", "2"]


def test_unknown_extension_rejected() -> None:
    with pytest.raises(ContractParseError):
        parse_contract(b"x", "file.xlsx")


def test_pdf_parser_uses_liteparse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import neurolegal.agent.review.parser as parser_mod

    def fake_extract(data: bytes) -> str:
        return "1. Предмет\nТекст.\n2. Оплата\n10 дней."

    monkeypatch.setattr(parser_mod, "_pdf_text", fake_extract)
    parsed = parse_contract(b"%PDF-1.4 fake", "contract.pdf")
    assert parsed.parser == "pdf"
    assert [s.number for s in parsed.sections] == ["1", "2"]
```

Run: `uv run pytest tests/unit/test_review_parser.py -q` → FAIL.

- [ ] **Step 2: Реализация**

```python
"""Парсеры договоров: DOCX (python-docx) и PDF (liteparse, локально)."""

import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from neurolegal.agent.review.sections import DocSection, build_sections


class ContractParseError(Exception):
    pass


@dataclass
class ParsedContract:
    sections: list[DocSection]
    full_text: str
    parser: str


def _docx_paragraphs(data: bytes) -> list[str]:
    try:
        doc = Document(BytesIO(data))
    except (PackageNotFoundError, ValueError) as exc:
        raise ContractParseError(f"Не удалось открыть DOCX: {exc}") from exc
    return [p.text for p in doc.paragraphs]


def _pdf_text(data: bytes) -> str:
    # liteparse принимает путь; точные имена kwargs зафиксированы в Task 1.
    from liteparse import LiteParse

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            result = LiteParse(ocr_language="rus").parse(Path(tmp.name))
        except Exception as exc:  # liteparse кидает свои типы; наружу — одно исключение
            raise ContractParseError(f"Не удалось извлечь текст из PDF: {exc}") from exc
    text: str = result.text
    return text


def parse_contract(data: bytes, filename: str) -> ParsedContract:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        paragraphs = _docx_paragraphs(data)
        parser = "docx"
    elif suffix == ".pdf":
        paragraphs = _pdf_text(data).splitlines()
        parser = "pdf"
    else:
        raise ContractParseError("Поддерживаются только файлы .docx и .pdf")
    sections, full_text = build_sections(paragraphs)
    if not full_text.strip():
        raise ContractParseError("Документ пуст или текст не извлечён")
    return ParsedContract(sections=sections, full_text=full_text, parser=parser)
```

Если фактический kwarg OCR-языка другой (Task 1 Step 2) — подставить его; если язык задаётся не в конструкторе, а в `parse()` — перенести.

- [ ] **Step 3: Тесты зелёные**

Run: `uv run pytest tests/unit/test_review_parser.py -q` → 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/agent/review/parser.py tests/unit/test_review_parser.py
git commit -m "feat(review): docx/pdf contract parsers over section builder"
```

---

### Task 5: Таблица documents + review-колонка + DocumentStore

**Files:**
- Modify: `src/neurolegal/agent/store/models.py` (DocumentRow, MessageRow.review)
- Create: `src/neurolegal/agent/store/document_store.py`
- Create: `alembic/versions/0007_documents_and_review.py`
- Modify: `src/neurolegal/agent/store/conversation_store.py` (append_message(review=…), StoredMessage.review)
- Test: `tests/unit/test_document_store.py`

**Interfaces:**
- Produces:
  - `DocumentRow`: колонки по спеке — `id String(36) PK`, `conversation_id FK conversations.id ondelete=CASCADE`, `filename String`, `content_hash String`, `mime String`, `parser String`, `status String` (`parsed|failed`), `error Text nullable`, `sections JSON` (список dict от `DocSection.__dict__`), `full_text Text`, `created_at DateTime(tz)`; `Index("ix_documents_conversation_id", "conversation_id")`.
  - `MessageRow.review: Mapped[dict | None] = mapped_column(JSON, nullable=True)`; `StoredMessage.review: dict | None`; `ConversationStore.append_message(..., review: dict[str, object] | None = None)`.
  - `DocumentStore(session)`: `async create_document(conversation_id, filename, content_hash, mime, parser, status, sections, full_text, error=None) -> str`; `async get_document(document_id) -> DocumentRow | None`; `async list_for_conversation(conversation_id) -> list[DocumentRow]`; `async commit()`. Flush-not-commit, как ConversationStore.

- [ ] **Step 1: Failing test (SQLite in-memory, паттерн существующих store-тестов — посмотреть `tests/unit/test_conversation_store*.py` и повторить фикстуру engine/session)**

```python
import pytest

from neurolegal.agent.store.document_store import DocumentStore

# фикстура session: скопировать из существующего теста conversation store
# (create_async_engine("sqlite+aiosqlite://"), Base.metadata.create_all, AsyncSession)


async def test_document_roundtrip(session) -> None:
    from neurolegal.agent.store.conversation_store import ConversationStore

    conv_store = ConversationStore(session)
    conv_id = await conv_store.create_conversation()
    store = DocumentStore(session)
    doc_id = await store.create_document(
        conversation_id=conv_id,
        filename="д.docx",
        content_hash="abc",
        mime="docx",
        parser="docx",
        status="parsed",
        sections=[{"number": "1", "title": "Предмет", "text": "т", "level": 1, "start": 0, "end": 1}],
        full_text="т",
    )
    await store.commit()
    row = await store.get_document(doc_id)
    assert row is not None and row.status == "parsed"
    docs = await store.list_for_conversation(conv_id)
    assert [d.id for d in docs] == [doc_id]


async def test_message_review_roundtrip(session) -> None:
    from neurolegal.agent.store.conversation_store import ConversationStore

    store = ConversationStore(session)
    conv_id = await store.create_conversation()
    await store.append_message(conv_id, "assistant", "отчёт", review={"playbook_id": "x"})
    await store.commit()
    history = await store.load_history(conv_id)
    assert history[0].review == {"playbook_id": "x"}
```

Run: `uv run pytest tests/unit/test_document_store.py -q` → FAIL.

- [ ] **Step 2: Модели + store + миграция**

`models.py` — добавить класс по Interfaces выше (стиль MessageRow). `document_store.py`:

```python
"""Repository над таблицей documents (flush-not-commit, как ConversationStore)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.agent.store.models import DocumentRow


class DocumentStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def create_document(
        self,
        conversation_id: str,
        filename: str,
        content_hash: str,
        mime: str,
        parser: str,
        status: str,
        sections: list[dict[str, object]],
        full_text: str,
        error: str | None = None,
    ) -> str:
        row = DocumentRow(
            conversation_id=conversation_id,
            filename=filename,
            content_hash=content_hash,
            mime=mime,
            parser=parser,
            status=status,
            sections=sections,
            full_text=full_text,
            error=error,
        )
        self._session.add(row)
        await self._session.flush()
        return row.id

    async def get_document(self, document_id: str) -> DocumentRow | None:
        return await self._session.get(DocumentRow, document_id)

    async def list_for_conversation(self, conversation_id: str) -> list[DocumentRow]:
        result = await self._session.execute(
            select(DocumentRow)
            .where(DocumentRow.conversation_id == conversation_id)
            .order_by(DocumentRow.created_at)
        )
        return list(result.scalars())
```

Миграция `0007_documents_and_review.py` (down_revision = "0006…", посмотреть точный id в `alembic/versions/0006_messages_web_sources.py`): `op.create_table("documents", …)` со всеми колонками + индекс; `op.add_column("messages", sa.Column("review", sa.JSON(), nullable=True))`; в `downgrade` — обратное.

`conversation_store.py`: добавить `review` в `StoredMessage`, параметр `review: dict[str, object] | None = None` в `append_message` → `MessageRow(..., review=review)`, прокинуть в `load_history`.

- [ ] **Step 3: Тесты зелёные + миграция применяется**

Run: `uv run pytest tests/unit/test_document_store.py tests/unit/ -q -k "store"` → PASS.
Run (если поднят докер-Postgres): `uv run neurolegal migrate` → `0007` applied. Если БД не поднята — пропустить, отметить в PR.

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/agent/store/ alembic/versions/0007_documents_and_review.py tests/unit/test_document_store.py
git commit -m "feat(review): documents table, message review column, DocumentStore"
```

---

### Task 6: Contracts DTO + SSE-события

**Files:**
- Create: `src/neurolegal/contracts/documents.py`
- Create: `src/neurolegal/contracts/review.py`
- Modify: `src/neurolegal/contracts/chat.py` (ReviewCommand, ChatRequest.command, MessageOut.review)
- Modify: `src/neurolegal/contracts/__init__.py` (реэкспорт)
- Modify: `src/neurolegal/agent/chat/events.py` (ReviewProgressEvent, ReviewReportEvent)
- Test: `tests/unit/test_contracts_review.py`

**Interfaces:**
- Produces (`contracts/documents.py`):

```python
class DocumentOutlineItem(BaseModel):
    number: str
    title: str | None = None

class DocumentInfo(BaseModel):
    id: str
    session_id: str
    filename: str
    status: Literal["parsed", "failed"]
    parser: str
    outline: list[DocumentOutlineItem]
    error: str | None = None

class PlaybookInfo(BaseModel):
    id: str
    name: str
    rules_count: int

class PlaybooksResponse(BaseModel):
    playbooks: list[PlaybookInfo]

class ConversationDocumentsResponse(BaseModel):
    documents: list[DocumentInfo]
```

- Produces (`contracts/review.py`):

```python
RiskLevel = Literal["high", "medium", "low"]
CoverageStatus = Literal["ok", "risk", "missing", "not_applicable"]
Verdict = Literal["confirmed", "overstated", "not_a_risk"]

class ReviewRisk(BaseModel):
    rule_id: str
    title: str
    level: RiskLevel
    verdict: Verdict
    section_number: str | None = None
    contract_quote: str
    explanation: str
    recommendation: str
    citations: list[Citation] = []      # from contracts.chat
    no_basis: bool = False

class ReviewCoverageItem(BaseModel):
    rule_id: str
    title: str
    status: CoverageStatus

class ReviewReportData(BaseModel):
    playbook_id: str
    playbook_name: str
    document_id: str
    risks: list[ReviewRisk]
    coverage: list[ReviewCoverageItem]
    disclaimer: str

class ReviewProgressEventData(BaseModel):
    rule_id: str
    title: str
    index: int
    total: int
    status: CoverageStatus | Literal["running"]

class ReviewReportEventData(ReviewReportData):
    pass
```

- Produces (`contracts/chat.py`):

```python
class ReviewCommand(BaseModel):   # живёт в chat.py — зависимостей не имеет
    type: Literal["risk_review"]
    document_id: str
    playbook_id: str

# ChatRequest: + command: ReviewCommand | None = None
# MessageOut: + review: "ReviewReportData | None" = None   # строковая аннотация!
```

  ВАЖНО (циклический импорт): `review.py` импортирует `Citation` из `chat.py`,
  поэтому `chat.py` НЕ может импортировать `review.py` напрямую. В `chat.py`
  использовать `if TYPE_CHECKING: from neurolegal.contracts.review import
  ReviewReportData` + строковую аннотацию поля, а в `contracts/__init__.py`
  после импорта обоих модулей вызвать `MessageOut.model_rebuild()`.

- Produces (`events.py`): `ReviewProgressEvent` (поля как EventData, `event="review_progress"`), `ReviewReportEvent(report: ReviewReportData)` (`event="review_report"`, `data` = `report.model_dump()`); оба добавить в union `AgentEvent`.

- [ ] **Step 1: Failing test**

```python
from neurolegal.agent.chat.events import ReviewProgressEvent, ReviewReportEvent
from neurolegal.contracts import ChatRequest, ReviewReportData


def test_chat_request_accepts_command() -> None:
    req = ChatRequest.model_validate(
        {
            "message": "Проверь договор",
            "command": {"type": "risk_review", "document_id": "d1", "playbook_id": "services_ru"},
        }
    )
    assert req.command is not None and req.command.playbook_id == "services_ru"


def test_review_events_shape() -> None:
    ev = ReviewProgressEvent(rule_id="r1", title="Оплата", index=1, total=15, status="running")
    assert ev.event == "review_progress" and ev.data["total"] == 15
    report = ReviewReportData(
        playbook_id="p", playbook_name="n", document_id="d",
        risks=[], coverage=[], disclaimer="…",
    )
    rev = ReviewReportEvent(report=report)
    assert rev.event == "review_report" and rev.data["playbook_id"] == "p"
```

Run: `uv run pytest tests/unit/test_contracts_review.py -q` → FAIL.

- [ ] **Step 2: Реализация** — файлы по Interfaces, реэкспорт всех новых имён в `contracts/__init__.py`, события по образцу `CitationsEvent`.

- [ ] **Step 3: Тесты зелёные**

Run: `uv run pytest tests/unit/test_contracts_review.py -q` → PASS.
Run: `uv run pytest tests/unit/test_contracts_openapi.py -q` → упадёт (снапшоты устарели) — это ОК, снапшоты регенерятся в Task 12; до тех пор коммитим с пометкой в теле коммита.

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/contracts/ src/neurolegal/agent/chat/events.py tests/unit/test_contracts_review.py
git commit -m "feat(review): DTOs and SSE events for documents and risk review

OpenAPI snapshots regenerated in a follow-up commit."
```

---

### Task 7: Роуты documents + playbooks

**Files:**
- Create: `src/neurolegal/agent/api/routes_documents.py`
- Modify: `src/neurolegal/agent/api/app.py` (include_router)
- Modify: `src/neurolegal/agent/api/deps.py` (get_document_store, get_playbooks)
- Test: `tests/unit/test_agent_documents_api.py`

**Interfaces:**
- Consumes: `parse_contract` (Task 4), `DocumentStore` (Task 5), `DocumentInfo/PlaybooksResponse` (Task 6), `load_playbooks` + `settings.playbooks_dir` (Tasks 1–2).
- Produces:
  - `POST /documents` — multipart `file: UploadFile`, `session_id: str | None = Form(None)`. Валидация: расширение `.docx|.pdf` и размер ≤ 20 МБ → иначе 422 `{"detail": "…"}`. Нет session_id → создать беседу (ConversationStore.create_conversation). Парсинг в `anyio.to_thread.run_sync` (CPU-bound). `ContractParseError` → row со `status="failed"`, `error=str(exc)`, ответ 200 с `status="failed"`. Ответ: `DocumentInfo` (outline = number+title из секций).
  - `GET /documents/{id}` → `DocumentInfo` | 404.
  - `GET /conversations/{id}/documents` → `ConversationDocumentsResponse`.
  - `GET /playbooks` → `PlaybooksResponse`.
  - deps: `@lru_cache get_playbooks() -> dict[str, Playbook]` (из `settings.playbooks_dir`); `get_document_store(session)` по образцу `get_store`.

- [ ] **Step 1: Failing test (ASGI + dependency_overrides, паттерн `-m api_with_mocks`-тестов; смотреть существующий `tests/unit/test_agent_web_sources.py` / аналог с httpx.AsyncClient + ASGITransport)**

```python
import io

import pytest
from httpx import ASGITransport, AsyncClient

# Фикстура app: взять паттерн создания приложения + override db-session на
# sqlite in-memory из существующих unit-тестов агентского API.


def _docx_bytes() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph("1. Предмет")
    doc.add_paragraph("Текст.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def test_upload_docx_creates_conversation_and_parses(client: AsyncClient) -> None:
    resp = await client.post(
        "/documents",
        files={"file": ("договор.docx", _docx_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "parsed"
    assert body["session_id"]
    assert body["outline"][0]["number"] == "1"


async def test_upload_wrong_extension_422(client: AsyncClient) -> None:
    resp = await client.post("/documents", files={"file": ("x.xlsx", b"data", "application/x")})
    assert resp.status_code == 422


async def test_playbooks_listed(client: AsyncClient) -> None:
    resp = await client.get("/playbooks")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["playbooks"]]
    assert "services_ru" in ids
```

Run: `uv run pytest tests/unit/test_agent_documents_api.py -q` → FAIL.

- [ ] **Step 2: Реализация routes_documents.py**

```python
"""Загрузка документов пользователя + каталог плейбуков."""

import hashlib
from pathlib import Path
from typing import Annotated

import anyio.to_thread
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from neurolegal.agent.api.deps import get_document_store, get_playbooks, get_store
from neurolegal.agent.review.parser import ContractParseError, ParsedContract, parse_contract
from neurolegal.agent.review.playbook import Playbook
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.document_store import DocumentStore
from neurolegal.contracts import (
    ConversationDocumentsResponse,
    DocumentInfo,
    DocumentOutlineItem,
    PlaybookInfo,
    PlaybooksResponse,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_ALLOWED = {".docx", ".pdf"}


def _info(row: object, session_id: str) -> DocumentInfo:  # row: DocumentRow
    return DocumentInfo(
        id=row.id,
        session_id=session_id,
        filename=row.filename,
        status=row.status,
        parser=row.parser,
        outline=[
            DocumentOutlineItem(number=s["number"], title=s.get("title"))
            for s in (row.sections or [])
        ],
        error=row.error,
    )


@router.post("/documents")
async def upload_document(
    file: UploadFile,
    store: Annotated[DocumentStore, Depends(get_document_store)],
    conv_store: Annotated[ConversationStore, Depends(get_store)],
    session_id: Annotated[str | None, Form()] = None,
) -> DocumentInfo:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=422, detail="Поддерживаются только файлы .docx и .pdf")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="Файл больше 20 МБ")

    if session_id is None:
        conversation_id = await conv_store.create_conversation()
    else:
        if not await conv_store.conversation_exists(session_id):
            raise HTTPException(status_code=404, detail="conversation not found")
        conversation_id = session_id

    status, error, sections, full_text, parser = "parsed", None, [], "", suffix.lstrip(".")
    try:
        parsed: ParsedContract = await anyio.to_thread.run_sync(
            parse_contract, data, file.filename or f"file{suffix}"
        )
        sections = [s.__dict__ for s in parsed.sections]
        full_text, parser = parsed.full_text, parsed.parser
    except ContractParseError as exc:
        status, error = "failed", str(exc)

    doc_id = await store.create_document(
        conversation_id=conversation_id,
        filename=file.filename or f"file{suffix}",
        content_hash=hashlib.sha256(data).hexdigest(),
        mime=suffix.lstrip("."),
        parser=parser,
        status=status,
        sections=sections,
        full_text=full_text,
        error=error,
    )
    await store.commit()
    row = await store.get_document(doc_id)
    assert row is not None
    return _info(row, conversation_id)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> DocumentInfo:
    row = await store.get_document(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return _info(row, row.conversation_id)


@router.get("/conversations/{conversation_id}/documents")
async def conversation_documents(
    conversation_id: str,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> ConversationDocumentsResponse:
    rows = await store.list_for_conversation(conversation_id)
    return ConversationDocumentsResponse(
        documents=[_info(r, conversation_id) for r in rows]
    )


@router.get("/playbooks")
async def playbooks(
    pbs: Annotated[dict[str, Playbook], Depends(get_playbooks)],
) -> PlaybooksResponse:
    return PlaybooksResponse(
        playbooks=[
            PlaybookInfo(id=p.id, name=p.name, rules_count=len(p.rules)) for p in pbs.values()
        ]
    )
```

deps.py:

```python
from neurolegal.agent.review.playbook import Playbook, load_playbooks
from neurolegal.agent.store.document_store import DocumentStore


@lru_cache(maxsize=1)
def get_playbooks() -> dict[str, Playbook]:
    return load_playbooks(settings.playbooks_dir)


def get_document_store(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> DocumentStore:
    return DocumentStore(session)
```

`app.py`: `app.include_router(routes_documents.router)` рядом с остальными. Тип `row: object` в `_info` замени на настоящий `DocumentRow` (mypy strict).

- [ ] **Step 3: Тесты зелёные**

Run: `uv run pytest tests/unit/test_agent_documents_api.py -q` → 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/agent/api/ tests/unit/test_agent_documents_api.py
git commit -m "feat(review): document upload/list and playbooks endpoints"
```

---

### Task 8: Тул read_document + документы в контексте агента

**Files:**
- Create: `src/neurolegal/agent/chat/tools/read_document.py`
- Modify: `src/neurolegal/agent/chat/tools/base.py` (ToolContext.document_sections)
- Modify: `src/neurolegal/agent/chat/agent.py` (конструктор + run())
- Modify: `src/neurolegal/agent/api/deps.py` (передать DocumentStore в ChatAgent)
- Test: `tests/unit/test_read_document_tool.py`

**Interfaces:**
- Consumes: `DocumentStore.list_for_conversation` (Task 5).
- Produces:
  - `ToolContext` + поле `documents: dict[str, list[dict[str, object]]] = field(default_factory=dict)` — `{document_id: sections}` подготавливает агент перед ходом (тул не ходит в БД сам — хендлеры синхронные по данным контекста, как ctx.acts).
  - `READ_DOCUMENT_TOOL = ToolSpec(name="read_document", …)` параметры: `document_id: string (required)`, `section_number: string (optional)`. Без section_number → оглавление + текст первых 4000 симв.; с ним → текст секции (или `{"error": "section not found"}`).
  - `handle(arguments, ctx) -> ToolOutcome` — `tool_result` JSON-строка.
  - `ChatAgent.__init__(…, document_store: DocumentStore | None = None, playbooks: dict[str, Playbook] | None = None)`.
  - В `ChatAgent.run()`: если есть document_store — `docs = await list_for_conversation(conversation_id)`; если docs непусты: (а) в system prompt добавляется блок `"\n\nВ беседе загружены документы:\n- {filename} (id={id}, секции: {numbers})…"`, (б) `READ_DOCUMENT_TOOL` добавляется в `tools_specs` для ЛЮБОГО интента (и LEGAL, и TEXT_TASK), (в) `ctx.documents` заполняется `{id: sections}` только для `status=="parsed"`.

- [ ] **Step 1: Failing test**

```python
import json

import pytest

from neurolegal.agent.chat.tools.base import ToolContext
from neurolegal.agent.chat.tools.read_document import handle

SECTIONS = [
    {"number": "1", "title": "Предмет", "text": "1. Предмет\nТекст.", "level": 1, "start": 0, "end": 10},
    {"number": "2", "title": "Оплата", "text": "2. Оплата\n10 дней.", "level": 1, "start": 11, "end": 20},
]


def _ctx() -> ToolContext:
    return ToolContext(rag_client=None, acts=None, tools=None, documents={"d1": SECTIONS})  # type: ignore[arg-type]


async def test_read_section() -> None:
    out = await handle({"document_id": "d1", "section_number": "2"}, _ctx())
    data = json.loads(out.tool_result)
    assert "10 дней" in data["text"]


async def test_outline_without_section() -> None:
    out = await handle({"document_id": "d1"}, _ctx())
    data = json.loads(out.tool_result)
    assert [s["number"] for s in data["outline"]] == ["1", "2"]


async def test_unknown_document() -> None:
    out = await handle({"document_id": "nope"}, _ctx())
    assert "error" in json.loads(out.tool_result)
```

Run: `uv run pytest tests/unit/test_read_document_tool.py -q` → FAIL.

- [ ] **Step 2: Реализация тула** (по образцу list_acts: ToolSpec + async handle, JSON ensure_ascii=False). Лимит текста в ответе 8000 симв. (`text[:8000]`).

- [ ] **Step 3: Интеграция в ChatAgent.run()** — по Interfaces. Тест интеграции:

```python
# в tests/unit/test_read_document_tool.py, с FakeLLM-паттерном из
# существующих тестов ChatAgent (см. tests/unit/test_chat_agent_settings.py):
# смоук: при наличии parsed-документа в tools_specs появляется read_document
# и системный промпт содержит имя файла.
```

Написать тест по этому паттерну: FakeLLM, InMemory-сессия SQLite, документ через DocumentStore, интент TEXT_TASK — проверить, что FakeLLM получил tools с `read_document` (FakeLLM записывает переданные tools в атрибут).

- [ ] **Step 4: deps.py** — `get_chat_agent(…)` получает `doc_store: Annotated[DocumentStore, Depends(get_document_store)]` и `playbooks=get_playbooks()`, передаёт в конструктор.

- [ ] **Step 5: Тесты зелёные + весь юнит-сьют**

Run: `uv run pytest tests/unit -q` → PASS (кроме test_contracts_openapi — ожидаемо до Task 12).

- [ ] **Step 6: Commit**

```bash
git add src/neurolegal/agent/chat/ src/neurolegal/agent/api/deps.py tests/unit/test_read_document_tool.py
git commit -m "feat(review): read_document tool + conversation documents in agent context"
```

---

### Task 9: ReviewEngine — маппинг и оценка (стадии 1–2)

**Files:**
- Create: `src/neurolegal/agent/review/engine.py`
- Test: `tests/unit/test_review_engine.py`

**Interfaces:**
- Consumes: `Playbook/PlaybookRule` (Task 2), `DocSection`-dicts (Task 5), `ChatLLM.stream(messages, tools)` (существующий), события Task 6.
- Produces:
  - `class ReviewEngineError(Exception)`
  - `class ReviewEngine:`
    - `__init__(self, llm: ChatLLM, rag_client: RagClient, acts: list[str] | None = None)`
    - `async def run(self, playbook: Playbook, document_id: str, sections: list[dict[str, object]], ) -> AsyncIterator[AgentEvent]` — yield'ит `ReviewProgressEvent` на каждое правило и в конце один `ReviewReportEvent`.
  - Внутренний хелпер `_structured(self, system: str, user: str, tool: ToolSpec) -> dict[str, object]`: собирает `ToolCallRequest` из `llm.stream(messages, [tool])`, при отсутствии tool-call — ОДИН повтор с добавленным в messages напоминанием "Ответь только вызовом инструмента"; после второй неудачи — `ReviewEngineError`.
  - `MAP_TOOL: ToolSpec` — name `"map_rules"`, parameters:
    `{"type":"object","properties":{"mapping":{"type":"array","items":{"type":"object","properties":{"rule_id":{"type":"string"},"section_numbers":{"type":"array","items":{"type":"string"}}},"required":["rule_id","section_numbers"]}}},"required":["mapping"]}`
  - `ASSESS_TOOL: ToolSpec` — name `"assess_rule"`, parameters:
    `{"type":"object","properties":{"status":{"type":"string","enum":["ok","risk","missing","not_applicable"]},"risk_level":{"type":"string","enum":["high","medium","low"]},"quote":{"type":"string"},"explanation":{"type":"string"},"recommendation":{"type":"string"}},"required":["status","explanation"]}`
- Логика стадии 1: один `_structured`-вызов; user-сообщение = оглавление (`number. title — первые 200 симв. текста` построчно) + список правил (`id: title — question`); правила, не упомянутые моделью или с пустым списком секций → «not_found».
- Логика стадии 2 (на правило): если not_found: `risk_if_missing` задан → риск `{status:"missing", level:risk_if_missing, quote:"", explanation:"Клауза не найдена в договоре"}` без LLM-вызова; иначе coverage `not_applicable`. Если секции найдены → `_structured(ASSESS_TOOL)`, user = question + полные тексты секций (суммарно ≤ 12000 симв., обрезать с пометкой). Anchors правила используются ТОЛЬКО как подсказка в prompt стадии 1 (маппинг решает модель).

- [ ] **Step 1: FakeLLM для тестов**

```python
"""FakeLLM: очередь заранее заданных ответов; каждый ответ — список LLMEvent."""

from neurolegal.agent.llm.types import ChatMessage, TextChunk, ToolCallRequest, ToolSpec


class FakeLLM:
    def __init__(self, scripted: list[list[object]]) -> None:
        self._scripted = list(scripted)
        self.calls: list[tuple[list[ChatMessage], list[ToolSpec]]] = []

    async def stream(self, messages: list[ChatMessage], tools: list[ToolSpec]):
        self.calls.append((messages, tools))
        for ev in self._scripted.pop(0):
            yield ev
```

- [ ] **Step 2: Failing tests стадий 1–2**

```python
import pytest

from neurolegal.agent.chat.events import ReviewProgressEvent, ReviewReportEvent
from neurolegal.agent.llm.types import ToolCallRequest
from neurolegal.agent.review.engine import ReviewEngine
from neurolegal.agent.review.playbook import Playbook

PB = Playbook.model_validate({
    "id": "t", "name": "Т",
    "rules": [
        {"id": "pay", "title": "Оплата", "question": "Срок оплаты?", "rag_queries": ["оплата"]},
        {"id": "ip", "title": "ИС", "question": "Права на РИД?", "risk_if_missing": "medium"},
    ],
})
SECTIONS = [
    {"number": "1", "title": "Оплата", "text": "1. Оплата в течение 90 дней после продажи третьим лицам.", "level": 1, "start": 0, "end": 50},
]


def _tc(name: str, args: dict) -> ToolCallRequest:
    return ToolCallRequest(id="x", name=name, arguments=args)


async def _collect(engine, playbook, sections):
    return [ev async for ev in engine.run(playbook, "doc1", sections)]


async def test_missing_rule_becomes_risk_without_llm() -> None:
    llm = FakeLLM([
        [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]},
                                        {"rule_id": "ip", "section_numbers": []}]})],
        [_tc("assess_rule", {"status": "risk", "risk_level": "high",
                             "quote": "в течение 90 дней после продажи",
                             "explanation": "Оплата зависит от третьих лиц",
                             "recommendation": "Фиксированный срок"})],
        # judge-вызовы появятся в Task 10; здесь judge отключён параметром
    ])
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert {r.rule_id for r in report.risks} == {"pay", "ip"}
    ip_risk = next(r for r in report.risks if r.rule_id == "ip")
    assert ip_risk.level == "medium" and "не найдена" in ip_risk.explanation
    coverage = {c.rule_id: c.status for c in report.coverage}
    assert coverage == {"pay": "risk", "ip": "missing"}
    progress = [e for e in events if isinstance(e, ReviewProgressEvent)]
    assert progress and progress[-1].total == 2


async def test_structured_retry_then_error() -> None:
    from neurolegal.agent.llm.types import TextChunk
    from neurolegal.agent.review.engine import ReviewEngineError

    llm = FakeLLM([[TextChunk(text="болтовня")], [TextChunk(text="опять")]])
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    with pytest.raises(ReviewEngineError):
        await _collect(engine, PB, SECTIONS)
```

Примечание: `rag_client=None` допустим в тестах стадий 1–2, т.к. граундинг (Task 10) при `judge_enabled=False` пропускается; в Task 10 сигнатура уточняется.

Run: `uv run pytest tests/unit/test_review_engine.py -q` → FAIL.

- [ ] **Step 3: Реализация стадий 1–2** — по Interfaces. Скелет:

```python
"""ReviewEngine: пятистадийный пайплайн проверки договора по плейбуку."""

import logging
from collections.abc import AsyncIterator

from neurolegal.agent.chat.events import AgentEvent, ReviewProgressEvent, ReviewReportEvent
from neurolegal.agent.llm.client import ChatLLM
from neurolegal.agent.llm.types import ChatMessage, ToolCallRequest, ToolSpec
from neurolegal.agent.review.playbook import Playbook, PlaybookRule
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.contracts import (
    ReviewCoverageItem,
    ReviewReportData,
    ReviewRisk,
)

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Черновая проверка. Выводы требуют подтверждения юриста; "
    "цитаты норм — только из найденных статей корпуса."
)

MAP_TOOL = ToolSpec(name="map_rules", description="…", parameters={…из Interfaces…})
ASSESS_TOOL = ToolSpec(name="assess_rule", description="…", parameters={…из Interfaces…})

MAP_SYSTEM = (
    "Ты сопоставляешь правила проверки договора с секциями документа. "
    "Для каждого правила укажи номера релевантных секций (пустой список, если таких нет). "
    "Отвечай только вызовом инструмента map_rules."
)
ASSESS_SYSTEM = (
    "Ты проверяешь договор по одному правилу. Оцени только по приведённому тексту секций. "
    "quote — дословная цитата из договора. Отвечай только вызовом инструмента assess_rule."
)


class ReviewEngineError(Exception):
    pass


class ReviewEngine:
    def __init__(
        self,
        llm: ChatLLM,
        rag_client: RagClient,
        acts: list[str] | None = None,
        judge_enabled: bool = True,
    ) -> None:
        ...

    async def run(
        self, playbook: Playbook, document_id: str, sections: list[dict[str, object]]
    ) -> AsyncIterator[AgentEvent]:
        mapping = await self._map(playbook, sections)          # стадия 1
        risks: list[ReviewRisk] = []
        coverage: list[ReviewCoverageItem] = []
        total = len(playbook.rules)
        for i, rule in enumerate(playbook.rules, start=1):
            yield ReviewProgressEvent(rule_id=rule.id, title=rule.title,
                                      index=i, total=total, status="running")
            risk, cov_status = await self._assess(rule, mapping.get(rule.id, []), sections)
            if risk is not None and self._judge_enabled:
                risk = await self._ground_and_judge(rule, risk)  # стадии 3–4 (Task 10)
            if risk is not None:
                risks.append(risk)
            coverage.append(ReviewCoverageItem(rule_id=rule.id, title=rule.title, status=cov_status))
            yield ReviewProgressEvent(rule_id=rule.id, title=rule.title,
                                      index=i, total=total, status=cov_status)
        yield ReviewReportEvent(report=ReviewReportData(
            playbook_id=playbook.id, playbook_name=playbook.name, document_id=document_id,
            risks=risks, coverage=coverage, disclaimer=DISCLAIMER,
        ))
```

`_assess` возвращает `(ReviewRisk | None, CoverageStatus)`; missing-ветка без LLM. При `status=="risk"` от модели строится `ReviewRisk(verdict="confirmed", …)` (verdict может быть понижен judge'ем в Task 10). `section_number` = первая замапленная секция.

- [ ] **Step 4: Тесты зелёные**

Run: `uv run pytest tests/unit/test_review_engine.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neurolegal/agent/review/engine.py tests/unit/test_review_engine.py
git commit -m "feat(review): engine stages 1-2 — rule mapping and clause assessment"
```

---

### Task 10: ReviewEngine — граундинг, judge, отчёт (стадии 3–5)

**Files:**
- Modify: `src/neurolegal/agent/review/engine.py`
- Test: `tests/unit/test_review_engine.py` (дополнить)

**Interfaces:**
- Consumes: `RagClient.search(query, acts=None, limit=…) -> list[SearchedArticle]` — проверить точную сигнатуру в `src/neurolegal/agent/tools/rag_client.py` и использовать её (включая имя метода; если метод называется иначе — например `search_articles` — взять фактическое имя).
- Produces:
  - `JUDGE_TOOL: ToolSpec` — name `"judge_risk"`, parameters:
    `{"type":"object","properties":{"verdict":{"type":"string","enum":["confirmed","overstated","not_a_risk"]},"citation_indexes":{"type":"array","items":{"type":"integer"}},"note":{"type":"string"}},"required":["verdict","citation_indexes"]}`
  - `_ground_and_judge(rule, risk) -> ReviewRisk | None`:
    1. Граундинг: для каждой `rule.rag_queries` (макс 2) — `rag_client.search(...)`, собрать до 6 уникальных статей. RAG упал → риск остаётся, `no_basis=True`, verdict не меняется (не терять риск из-за отказа поиска), лог warning.
    2. Judge: `_structured(JUDGE_TOOL)`; user = правило + риск (quote, explanation) + нумерованный список найденных статей (`[1] ст. N АКТ — title — первые 300 симв.`). Модель выбирает `citation_indexes` — только ВЫБОР из списка, придумать статью невозможно (валидатор по построению: индексы вне диапазона игнорируются).
    3. `verdict=="not_a_risk"` → вернуть None, coverage у этого правила становится `ok` (перезаписать).
    4. Иначе — вернуть risk с `verdict`, `citations` (выбранные статьи → `Citation`, поля как в `agent.py::_citation`), `no_basis = citations == []`.
  - `_structured` ошибка на judge → риск сохраняется как есть (verdict `confirmed`, `no_basis=True`) — проверка не падает целиком из-за одного judge-вызова; лог warning.

- [ ] **Step 1: Failing tests**

```python
class FakeRag:
    def __init__(self, articles):  # articles: list[SearchedArticle]
        self._articles = articles
        self.queries: list[str] = []

    async def search(self, query, acts=None, limit=8):  # сигнатуру сверить с RagClient
        self.queries.append(query)
        return self._articles


def _article(number="781", act="ГК РФ"):
    from neurolegal.contracts import SearchedArticle
    return SearchedArticle(  # заполнить обязательные поля фактической модели
        article_id=1, act_short_name=act, act_kind="code", number=number,
        title="Оплата услуг", full_text="Заказчик обязан оплатить…", score=0.9,
    )


async def test_judge_selects_citations_by_index() -> None:
    llm = FakeLLM([
        [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]},
                                        {"rule_id": "ip", "section_numbers": []}]})],
        [_tc("assess_rule", {"status": "risk", "risk_level": "high", "quote": "90 дней",
                             "explanation": "зависимость от третьих лиц", "recommendation": "фикс. срок"})],
        [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [1, 99]})],  # 99 — вне диапазона
    ])
    rag = FakeRag([_article()])
    engine = ReviewEngine(llm=llm, rag_client=rag)  # judge включён по умолчанию
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert [c.number for c in pay.citations] == ["781"]   # 99 отброшен валидатором
    assert pay.no_basis is False
    assert rag.queries == ["оплата"]


async def test_not_a_risk_flips_coverage_to_ok() -> None:
    llm = FakeLLM([
        [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]},
                                        {"rule_id": "ip", "section_numbers": []}]})],
        [_tc("assess_rule", {"status": "risk", "risk_level": "low", "quote": "х",
                             "explanation": "спорно", "recommendation": ""})],
        [_tc("judge_risk", {"verdict": "not_a_risk", "citation_indexes": []})],
    ])
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([]))
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert all(r.rule_id != "pay" for r in report.risks)
    coverage = {c.rule_id: c.status for c in report.coverage}
    assert coverage["pay"] == "ok"


async def test_rag_outage_keeps_risk_with_no_basis() -> None:
    class DownRag:
        async def search(self, query, acts=None, limit=8):
            from neurolegal.agent.tools.rag_client import RagClientError
            raise RagClientError("down")

    llm = FakeLLM([
        [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]},
                                        {"rule_id": "ip", "section_numbers": []}]})],
        [_tc("assess_rule", {"status": "risk", "risk_level": "high", "quote": "90 дней",
                             "explanation": "…", "recommendation": "…"})],
        [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": []})],
    ])
    engine = ReviewEngine(llm=llm, rag_client=DownRag())
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert pay.no_basis is True and pay.citations == []
```

Run: `uv run pytest tests/unit/test_review_engine.py -q` → новые FAIL.

- [ ] **Step 2: Реализация `_ground_and_judge`** по Interfaces (внутри `run()` уже вызывается). Coverage-переворот на `not_a_risk`: `_assess` возвращает status, но окончательная запись в coverage происходит ПОСЛЕ judge — перенести append coverage за judge-вызов.

- [ ] **Step 3: Тесты зелёные (все 5+)**

Run: `uv run pytest tests/unit/test_review_engine.py -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/agent/review/engine.py tests/unit/test_review_engine.py
git commit -m "feat(review): engine stages 3-5 — grounding, judge with index-picked citations, report"
```

---

### Task 11: Команда risk_review в чате

**Files:**
- Modify: `src/neurolegal/agent/chat/agent.py` (метод run_review)
- Modify: `src/neurolegal/agent/api/routes_chat.py` (ветка command)
- Test: `tests/unit/test_chat_review_command.py`

**Interfaces:**
- Consumes: `ReviewEngine` (Tasks 9–10), `DocumentStore` (Task 5), `ReviewCommand` (Task 6), `get_playbooks` (Task 7).
- Produces:
  - `ChatAgent.run_review(conversation_id: str, command: ReviewCommand, user_message: str) -> AsyncIterator[AgentEvent]`:
    1. Валидация: документ существует, `document.conversation_id == conversation_id`, `status=="parsed"`, плейбук известен — иначе yield `ErrorEvent(detail=…)` и return (без записи сообщений).
    2. `append_message(user)` + commit (текст = `user_message`, фронт шлёт «Проверить договор "{filename}" по плейбуку {name}»).
    3. `engine = ReviewEngine(llm=self._review_llm or self._llm, rag_client=self._rag)`; прокинуть события; поймать `ReviewReportEvent` → `report`. Новый ctor-параметр `ChatAgent(…, review_llm: ChatLLM | None = None)`; в `deps.py` — `@lru_cache get_review_llm()`: если `settings.review_model` задан, вернуть `OpenRouterChatClient(model=settings.review_model, …как get_llm…)`, иначе `None` (так `NEUROLEGAL_REVIEW_MODEL` из Task 1 реально используется).
    4. `ReviewEngineError` → yield ErrorEvent, БЕЗ записи assistant-сообщения (частичный отчёт не сохраняется), return.
    5. Markdown-резюме: `_review_summary(report) -> str` — H-строка «Проверка по плейбуку {name}», счётчики рисков по уровням, топ-3 риска строками «— [high] {title}: {explanation первые 200}», строка покрытия «Покрытие: N правил, рисков M, отсутствует K».
    6. `append_message(conversation_id, "assistant", summary, review=report.model_dump())` + commit; yield DoneEvent(message_id).
  - `routes_chat.py`: `if req.command is not None: gen = agent.run_review(conversation_id, req.command, req.message) else: gen = agent.run(...)` — остальной SSE-код без изменений.
  - `GET /conversations/{id}/messages` (routes_conversations.py): прокинуть `review` из StoredMessage в MessageOut.

- [ ] **Step 1: Failing test** — паттерн FakeLLM + SQLite-сессия; полный сценарий: создать беседу + parsed-документ, вызвать `run_review`, собрать события:

```python
async def test_run_review_persists_report(...) -> None:
    # FakeLLM со скриптом: map → assess(ok) для всех правил мини-плейбука
    # (1 правило, status="ok") → отчёт без рисков.
    events = [ev async for ev in agent.run_review(conv_id, cmd, "Проверить договор")]
    assert any(isinstance(e, ReviewReportEvent) for e in events)
    done = next(e for e in events if isinstance(e, DoneEvent))
    history = await store.load_history(conv_id)
    assert history[-1].review is not None
    assert history[-1].review["coverage"][0]["status"] == "ok"


async def test_run_review_wrong_conversation_rejected(...) -> None:
    # документ из другой беседы → первый event = ErrorEvent, сообщений не добавилось
```

Run → FAIL.

- [ ] **Step 2: Реализация** по Interfaces. ChatAgent получает playbooks в конструктор (уже с Task 8).

- [ ] **Step 3: Тесты зелёные; полный сьют**

Run: `uv run pytest tests/unit -q` → PASS (кроме openapi-снапшотов).

- [ ] **Step 4: Commit**

```bash
git add src/neurolegal/agent/chat/agent.py src/neurolegal/agent/api/ tests/unit/test_chat_review_command.py
git commit -m "feat(review): risk_review chat command wired into SSE turn"
```

---

### Task 12: OpenAPI-снапшоты + TS-типы

**Files:**
- Modify: `frontend/openapi/*.json`, `tests/data/openapi/*.json`, `frontend/src/api/generated/agent.ts`
- Modify: `frontend/src/api/types.ts` (алиасы новых схем)

- [ ] **Step 1: Регенерация**

```bash
uv run python -m scripts.generate_openapi
npm --prefix frontend run openapi:generate
cp frontend/openapi/*.json tests/data/openapi/  # если снапшоты тестов лежат отдельно — проверить путь в test_contracts_openapi.py и обновить так, как ожидает тест
```

- [ ] **Step 2: Алиасы в types.ts** (по образцу существующих):

```ts
export type DocumentInfo = components["schemas"]["DocumentInfo"];
export type PlaybookInfo = components["schemas"]["PlaybookInfo"];
export type ReviewReport = components["schemas"]["ReviewReportData"];
export type ReviewProgress = components["schemas"]["ReviewProgressEventData"];
export type ReviewRisk = components["schemas"]["ReviewRisk"];
export type ReviewCoverageItem = components["schemas"]["ReviewCoverageItem"];
```

и добавить `review_progress`/`review_report` в union `ServerEvent` (структура union — см. текущий types.ts, повторить стиль).

- [ ] **Step 3: Гейт зелёный**

Run: `uv run pytest tests/unit/test_contracts_openapi.py -q` → PASS.
Run: `npm --prefix frontend run build` → OK (tsc без ошибок).

- [ ] **Step 4: Commit**

```bash
git add frontend/openapi tests/data/openapi frontend/src/api src/neurolegal/agent/api/static
git commit -m "chore(contracts): regenerate OpenAPI snapshots and TS types for review API"
```

---

### Task 13: Фронт — api-клиент и состояние

**Files:**
- Modify: `frontend/src/api/client.ts` (uploadDocument, listPlaybooks, getConversationDocuments)
- Modify: `frontend/src/api/sse.ts` (ChatParams.command)
- Modify: `frontend/src/state/chatReducer.ts` (+documents, reviewProgress, review в message)
- Modify: `frontend/src/state/ChatContext.tsx` (sendReview, uploadFile)

**Interfaces:**
- Produces (client.ts):

```ts
export async function uploadDocument(file: File, sessionId: string | null): Promise<DocumentInfo> {
  const form = new FormData();
  form.append("file", file);
  if (sessionId) form.append("session_id", sessionId);
  const resp = await fetch("/documents", { method: "POST", body: form });
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "string" ? detail : `upload → ${resp.status}`);
  }
  return (await resp.json()) as DocumentInfo;
}

export async function listPlaybooks(): Promise<PlaybookInfo[]> { /* getJson("/playbooks").playbooks */ }
export async function getConversationDocuments(id: string): Promise<DocumentInfo[]> { /* getJson(`/conversations/${id}/documents`).documents */ }
```

- Produces (sse.ts): `ChatParams` + `command?: { type: "risk_review"; document_id: string; playbook_id: string } | null`; body JSON включает `command: params.command ?? null`.
- Produces (reducer):
  - `ChatState` + `documents: DocumentInfo[]`, `reviewProgress: ReviewProgress | null`.
  - Действия: `SET_DOCUMENTS` (загрузка беседы), `DOCUMENT_ADDED` (после upload; также устанавливает sessionId, если беседы не было).
  - SSE-кейсы: `"review_progress"` → `reviewProgress = data`; `"review_report"` → прикрепить `review` к стримящемуся сообщению (по паттерну кейса `"citations"`), сбросить `reviewProgress`; в `FINISH_TURN`/`TURN_FAILED`/`NEW_CHAT`/`OPEN_CONVERSATION` — `reviewProgress: null`, documents загружаются в `OPEN_CONVERSATION`-поток (ChatContext делает fetch).
  - `Message`-тип фронта (`types.ts` или локальный) + `review?: ReviewReport | null` — восстанавливается из истории (`MessageOut.review`).
- Produces (ChatContext): `uploadFile(file: File): Promise<DocumentInfo>` (вызывает uploadDocument с текущим sessionId, диспатчит DOCUMENT_ADDED); `sendReview(documentId: string, playbookId: string, label: string): Promise<void>` — как `send`, но с command и message=label.

- [ ] **Step 1: Реализовать по Interfaces** (тестов на фронте в репо нет — гейт: tsc).
- [ ] **Step 2: Проверка типов** — `npm --prefix frontend run build` → OK.
- [ ] **Step 3: Commit**

```bash
git add frontend/src src/neurolegal/agent/api/static
git commit -m "feat(chat-ui): document upload state, review command plumbing"
```

---

### Task 14: Фронт — UI загрузки, пикер плейбука, отчёт

**Files:**
- Modify: `frontend/src/components/Composer.tsx` (скрепка)
- Create: `frontend/src/components/DocumentChip.tsx` (чип файла + меню «Проверить на риски»)
- Create: `frontend/src/components/ReviewReportView.tsx` (таблица рисков + покрытие)
- Modify: `frontend/src/components/AssistantMessage.tsx` (рендер review)
- Modify: `frontend/src/components/WorkingIndicator.tsx` или MessageList (прогресс-чек-лист)
- Modify: `frontend/src/styles.css` (стили по токенам)

**Interfaces:**
- Consumes: `uploadFile`, `sendReview`, `state.documents`, `state.reviewProgress`, `message.review` (Task 13); `listPlaybooks` (кэшировать в ChatContext при первом открытии меню).
- Produces (поведение):
  - Composer: кнопка-скрепка (`Paperclip` из lucide-react) слева от SourceSelector; `<input type="file" accept=".docx,.pdf" hidden>`; во время аплоада — спиннер на скрепке; ошибка → баннер (`SET_BANNER`, существующий механизм).
  - Полоса чипов документов над композером (рендерится, если `state.documents.length > 0`): имя файла, статус (`failed` — приглушённый красный текст ошибки в title), меню по клику: пункты плейбуков → `sendReview(doc.id, pb.id, `Проверить «${doc.filename}»: ${pb.name}`)`. Дизайн: монохромные чипы, без заливок.
  - Прогресс: пока `state.reviewProgress != null` — вместо/рядом с WorkingIndicator строка «Проверка: {title} ({index}/{total})» + тонкий progress-бар (accent).
  - `ReviewReportView({ report })`: заголовок «Проверка по плейбуку {playbook_name}»; таблица рисков (колонки: уровень — badge-точка цветом high=--accent/medium/low серые, правило, цитата договора моноширинным блоком, норма (CitationChip на каждую citation — переиспользовать существующий компонент), рекомендация); блок «Покрытие» — компактная сетка `title → статус` (✓ ok / ! risk / — not_applicable / ∅ missing); дисклеймер `p.disclaimer` внизу. Риски с `no_basis` показывают пометку «норма не найдена» вместо цитат.
  - AssistantMessage: если `message.review` — рендерить `ReviewReportView` под текстом сообщения.

- [ ] **Step 1: Реализовать компоненты и стили по Interfaces.**
- [ ] **Step 2: `npm --prefix frontend run build`** → OK; глазами проверить в `make dev` (или vite dev): загрузка файла, чипы, запуск проверки (можно с локальным LLM/ключом).
- [ ] **Step 3: Commit**

```bash
git add frontend/src frontend/index.html src/neurolegal/agent/api/static
git commit -m "feat(chat-ui): file upload, playbook picker, risk report and coverage render"
```

---

### Task 15: Плейбуки поставки и аренды

**Files:**
- Create: `playbooks/supply_ru.yaml`
- Create: `playbooks/lease_ru.yaml`
- Test: покрыт существующим `test_shipped_playbooks_are_valid`

- [ ] **Step 1: supply_ru.yaml — 12 правил** (структура как services_ru; правила: предмет/наименование и количество товара (ст. 455, 465 ГК; risk_if_missing high), сроки поставки (ст. 508), цена и оплата (ст. 516), качество и гарантия (ст. 469, 470), комплектность (ст. 478), приёмка по количеству/качеству и сроки уведомления (ст. 513, 483; high), переход права собственности и риска (ст. 459, 491), неустойка за просрочку (ст. 330, 521), односторонний отказ (ст. 523), возврат/недопоставка (ст. 511), форс-мажор (ст. 401), претензии и подсудность (ст. 4 АПК). Каждое правило: anchors, question, law_hints, rag_queries — по образцу services_ru, вопросы формулировать про баланс сторон и скрытые условия.)

- [ ] **Step 2: lease_ru.yaml — 12 правил** (объект аренды и его идентификация (ст. 607 ГК; high), срок аренды и госрегистрация при ≥ 1 года для недвижимости (ст. 609, 651; high), арендная плата и порядок изменения — не чаще раза в год (ст. 614), обеспечительный платёж (ст. 381.1), передача и возврат по акту (ст. 611, 622), текущий/капитальный ремонт (ст. 616), улучшения (ст. 623), субаренда (ст. 615), досрочное расторжение арендодателем/арендатором (ст. 619, 620), преимущественное право (ст. 621), ответственность и коммунальные платежи, претензии/подсудность.)

- [ ] **Step 3: Тест** — `uv run pytest tests/unit/test_review_playbook.py -q` → PASS (3 плейбука валидны).

- [ ] **Step 4: Commit**

```bash
git add playbooks/
git commit -m "feat(review): supply and lease playbooks"
```

---

### Task 16: Финальная верификация

- [ ] **Step 1:** `make check` (lint + typecheck + unit) → зелёный.
- [ ] **Step 2:** `uv run python -m scripts.generate_openapi && git diff --exit-code frontend/openapi tests/data/openapi` → пусто (снапшоты актуальны).
- [ ] **Step 3:** `npm --prefix frontend run build` → бандл пересобран, `git status` показывает только ожидаемые файлы.
- [ ] **Step 4:** Ручной e2e по критериям приёмки спеки (см. spec §Критерии): `make dev`, загрузить реальный DOCX-договор услуг, задать вопрос по документу, запустить проверку по services_ru, дождаться отчёта ≤ 3 мин, перезагрузить страницу — отчёт восстановился. Прогнать также PDF (текстовый слой). Скан — только при установленном Tesseract.
- [ ] **Step 5:** `uv run neurolegal migrate` на локальном Postgres — миграция 0007 применяется чисто.
- [ ] **Step 6: Commit остаточных артефактов** (если есть) + отметить в plan.md статус P0.
