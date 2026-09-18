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
