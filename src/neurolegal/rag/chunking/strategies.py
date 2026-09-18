import re
from collections.abc import Iterable
from enum import StrEnum
from uuid import uuid4

from neurolegal.core.domain import EMBEDDING_DIM, Article, Chunk

POINT_PATTERN = re.compile(r"(?:^|\s)(\d+(?:\.\d+)?)\.\s+", re.MULTILINE)


class ChunkStrategy(StrEnum):
    PER_POINT = "per_point"
    SLIDING = "sliding"


def chunk_article(
    article: Article,
    *,
    strategy: ChunkStrategy = ChunkStrategy.PER_POINT,
    max_chars: int = 800,
    overlap: int = 100,
    act_short_name: str,
) -> list[Chunk]:
    # article.points (when populated by the parser) takes precedence over `strategy`.
    if article.points is not None:
        points: list[tuple[str | None, str]] = [(p.number, p.text) for p in article.points]
    elif strategy == ChunkStrategy.PER_POINT:
        points = list(_split_points(article.full_text))
    else:
        points = list(_sliding(article.full_text, max_chars=max_chars, overlap=overlap))

    structure_path: dict[str, str] = {"article": article.number}

    chunks: list[Chunk] = []
    for ordinal, (part_num, text) in enumerate(points, start=1):
        chunks.append(
            Chunk(
                id=uuid4(),
                article_id=article.id,
                act_id=article.act_id,
                path=_format_path(article.number, part_num, act_short_name),
                part_number=part_num,
                point_number=None,
                sub_point_number=None,
                text=text,
                ordinal=ordinal,
                embedding=[0.0] * EMBEDDING_DIM,
                structure_path=structure_path,
            )
        )
    return chunks


def _split_points(text: str) -> Iterable[tuple[str | None, str]]:
    matches = list(POINT_PATTERN.finditer(text))
    if not matches:
        yield None, text.strip()
        return
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield m.group(1), text[start:end].strip()


def _sliding(text: str, *, max_chars: int, overlap: int) -> Iterable[tuple[str | None, str]]:
    if len(text) <= max_chars:
        yield None, text.strip()
        return
    pos = 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
        yield None, text[pos:end].strip()
        pos += max_chars - overlap


def _format_path(article_number: str, part_number: str | None, act_short_name: str) -> str:
    if part_number:
        return f"ст. {article_number} ч. {part_number} {act_short_name}"
    return f"ст. {article_number} {act_short_name}"
