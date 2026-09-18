from datetime import datetime
from pathlib import Path

from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry
from neurolegal.rag.sources_view import build_sources
from neurolegal.rag.store.admin import ActDbStats


def _entry(code_id: str, branch: str | None = "Гражданское право") -> ManifestEntry:
    return ManifestEntry(
        code_id=code_id,
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс РФ",
        branch=branch,
        docx_path=Path("x.docx"),
    )


def _stats(source_doc_id: str) -> ActDbStats:
    return ActDbStats(
        act_id="a1",
        source_doc_id=source_doc_id,
        short_name="ГК РФ",
        full_name="Гражданский кодекс РФ",
        kind="codex",
        ingested_at=datetime(2026, 1, 1),
        articles_count=10,
        chunks_count=50,
    )


def test_ingested_entry_is_in_corpus() -> None:
    manifest = Manifest(entries={"ГК-1": _entry("ГК-1")})
    sid = manifest.entries["ГК-1"].source_doc_id
    out = build_sources(manifest, [_stats(sid)])
    assert len(out) == 1
    assert out[0].status == "in_corpus"
    assert out[0].source_doc_id == sid
    assert out[0].branch == "Гражданское право"


def test_entry_without_stats_is_planned() -> None:
    manifest = Manifest(entries={"ГК-1": _entry("ГК-1")})
    out = build_sources(manifest, [])
    assert out[0].status == "planned"


def test_sorted_by_short_name_then_full_name() -> None:
    manifest = Manifest(
        entries={
            "Б": _entry("Б"),
            "А": ManifestEntry(
                code_id="А",
                kind="codex",
                short_name="АПК РФ",
                full_name="Арбитражный процессуальный кодекс РФ",
                branch="Арбитражный процесс",
                docx_path=Path("x.docx"),
            ),
        }
    )
    out = build_sources(manifest, [])
    assert [s.short_name for s in out] == ["АПК РФ", "ГК РФ"]


def test_output_has_no_unsafe_fields() -> None:
    manifest = Manifest(entries={"ГК-1": _entry("ГК-1")})
    sid = manifest.entries["ГК-1"].source_doc_id
    dumped = build_sources(manifest, [_stats(sid)])[0].model_dump()
    for unsafe in (
        "docx_path",
        "file_path",
        "mtime",
        "chunks_count",
        "articles_count",
        "ingested_at",
    ):
        assert unsafe not in dumped
