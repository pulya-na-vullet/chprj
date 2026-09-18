from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from docx import Document

from neurolegal.core.domain import (
    Article,
    ArticlePoint,
    LegalAct,
    RawDocument,
    StructuredDoc,
    StructureNode,
    StructureType,
)
from neurolegal.rag.acquisition.manifest import Manifest

logger = logging.getLogger(__name__)


class DocxParseError(Exception):
    pass


_BOILERPLATE_TOKENS = (
    "КонсультантПлюс",
    "www.consultant.ru",
    "Дата сохранения",
    "Документ предоставлен",
)
_FZ_NUMBER_RE = re.compile(r"^N\s+\d+[А-Яа-я\-]*-ФЗ$")
_HEADING_RE = re.compile(r"^(Часть|Раздел|Подраздел|Глава|Параграф|§)\s+([IVXLCDM\d.]+)\.?\s*(.*)$")
_ARTICLE_RE = re.compile(r"^Статья\s+(\d+(?:\.\d+)*(?:-\d+)?)\.?\s*(.*)$")
_POINT_RE = re.compile(r"^(\d+(?:\.\d+)?)\.\s+(.*)$")

_HEADING_TYPE: dict[str, StructureType] = {
    "Часть": "part",
    "Раздел": "section",
    "Подраздел": "subsection",
    "Глава": "chapter",
    "Параграф": "paragraph",
    "§": "paragraph",
}


@dataclass
class _PendingArticle:
    number: str
    title: str | None
    parent_node_id: UUID | None
    raw_paragraphs: list[str] = field(default_factory=list)


class DocxParser:
    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest

    def parse(self, raw: RawDocument) -> StructuredDoc:
        entry = next(
            (e for e in self._manifest.entries.values() if e.source_doc_id == raw.source_doc_id),
            None,
        )
        if entry is None:
            raise DocxParseError(f"no manifest entry matches source_doc_id={raw.source_doc_id!r}")

        try:
            document = Document(io.BytesIO(raw.body_bytes))
        except Exception as exc:
            raise DocxParseError(f"cannot open .docx: {exc}") from exc

        act = LegalAct(
            id=uuid4(),
            kind=entry.kind,
            short_name=entry.short_name,
            full_name=entry.full_name,
            source=raw.source,
            source_doc_id=raw.source_doc_id,
            redaction=entry.redaction,
            ingested_at=datetime.now(UTC),
        )

        nodes: list[StructureNode] = []
        articles: list[Article] = []
        stack: list[StructureNode] = []
        article_ordinal = 0
        pending: _PendingArticle | None = None
        seen_first_heading = False

        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if _is_boilerplate(text, seen_first_heading):
                continue

            heading = _parse_heading(text)
            if heading is not None:
                seen_first_heading = True
                kind, number, title = heading
                if pending is not None:
                    articles.append(_finalize_article(pending, act.id, article_ordinal))
                    pending = None
                _push_node(nodes, stack, act.id, kind, number, title)
                continue

            article_match = _ARTICLE_RE.match(text)
            if article_match is not None:
                seen_first_heading = True
                if pending is not None:
                    articles.append(_finalize_article(pending, act.id, article_ordinal))
                article_ordinal += 1
                num, title_part = article_match.group(1), article_match.group(2).strip() or None
                parent_node_id = stack[-1].id if stack else None
                pending = _PendingArticle(
                    number=num, title=title_part, parent_node_id=parent_node_id
                )
                continue

            if pending is not None:
                pending.raw_paragraphs.append(text)
            # else: text before any structural heading → discard

        if pending is not None:
            articles.append(_finalize_article(pending, act.id, article_ordinal))

        articles = _dedupe_by_number(articles)
        # Drop tombstone articles ("Утратила силу...") that have no body —
        # they produce empty chunks and pollute the HNSW index with embeddings
        # of empty strings.
        articles = [a for a in articles if a.full_text.strip()]

        if not articles:
            raise DocxParseError(f"no articles detected in {raw.source_doc_id}")

        return StructuredDoc(act=act, structure_nodes=nodes, articles=articles)


def _dedupe_by_number(arts: list[Article]) -> list[Article]:
    """Collapse duplicate (number) entries within one act, preferring the
    non-empty body. Russian codices keep an 'Утратила силу' tombstone for
    repealed articles; when a later chapter reuses the same number, both
    appear in the source. The non-empty entry is the live article.
    """
    keep: dict[str, Article] = {}
    for a in arts:
        existing = keep.get(a.number)
        if existing is None or (not existing.full_text.strip() and a.full_text.strip()):
            keep[a.number] = a
    return [a for a in arts if keep.get(a.number) is a]


def _is_boilerplate(text: str, seen_first_heading: bool) -> bool:
    for token in _BOILERPLATE_TOKENS:
        if token in text:
            return True
    return bool(not seen_first_heading and _FZ_NUMBER_RE.match(text))


def _parse_heading(text: str) -> tuple[StructureType, str, str | None] | None:
    m = _HEADING_RE.match(text)
    if m is None:
        return None
    word, number, title_raw = m.group(1), m.group(2), m.group(3).strip()
    kind = _HEADING_TYPE[word]
    title = title_raw or None
    return kind, number, title


_LEVEL_ORDER: dict[StructureType, int] = {
    "part": 1,
    "section": 2,
    "subsection": 3,
    "chapter": 4,
    "paragraph": 5,
}


def _push_node(
    nodes: list[StructureNode],
    stack: list[StructureNode],
    act_id: UUID,
    kind: StructureType,
    number: str,
    title: str | None,
) -> StructureNode:
    new_level = _LEVEL_ORDER[kind]
    while stack and _LEVEL_ORDER[stack[-1].type] >= new_level:
        stack.pop()
    parent_id = stack[-1].id if stack else None
    node = StructureNode(
        id=uuid4(),
        act_id=act_id,
        parent_id=parent_id,
        type=kind,
        number=number,
        title=title,
        ordinal=len(nodes) + 1,
    )
    nodes.append(node)
    stack.append(node)
    return node


def _finalize_article(p: _PendingArticle, act_id: UUID, ordinal: int) -> Article:
    points = _group_points(p.raw_paragraphs)
    full_text = "\n\n".join(pt.text for pt in points) if points else ""
    return Article(
        id=uuid4(),
        act_id=act_id,
        parent_node_id=p.parent_node_id,
        number=p.number,
        title=p.title,
        full_text=full_text,
        ordinal=ordinal,
        points=points or None,
    )


def _group_points(paragraphs: list[str]) -> list[ArticlePoint]:
    """Group raw body paragraphs into ArticlePoints."""
    points: list[ArticlePoint] = []
    current_number: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            points.append(
                ArticlePoint(number=current_number, text="\n".join(current_lines).strip())
            )
            current_lines = []

    for para in paragraphs:
        m_point = _POINT_RE.match(para)
        if m_point is not None:
            flush()
            current_number = m_point.group(1)
            current_lines = [m_point.group(2)]
            continue
        # subpoint or continuation — append to current point
        current_lines.append(para)

    flush()
    return points
