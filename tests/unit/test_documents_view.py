"""build_documents: матрица статусов манифест x БД x mtime x активный джоб."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from neurolegal.rag.acquisition.corpus_store import ObjectInfo
from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry
from neurolegal.rag.documents_view import build_documents
from neurolegal.rag.store.admin import ActDbStats

NOW = datetime.now(UTC)


def _entry(code_id: str, docx: str) -> ManifestEntry:
    return ManifestEntry(
        code_id=code_id,
        kind="codex",
        short_name=f"{code_id} РФ",
        full_name=f"Кодекс {code_id}",
        docx_path=Path(docx),
    )


def _stats(sid: str, ingested_at: datetime) -> ActDbStats:
    return ActDbStats(
        act_id="a1",
        source_doc_id=sid,
        short_name="ГК РФ",
        full_name="Кодекс",
        kind="codex",
        ingested_at=ingested_at,
        articles_count=10,
        chunks_count=40,
    )


def test_not_ingested_when_no_db_row(tmp_path: Path) -> None:
    (tmp_path / "gk.docx").write_bytes(b"x")
    manifest = Manifest(entries={"ГК": _entry("ГК", "gk.docx")})
    docs = build_documents(manifest, [], None, base_dir=tmp_path)
    assert docs[0].status == "not_ingested"
    assert docs[0].file_exists is True
    assert docs[0].articles_count is None


def test_ingested_when_db_newer_than_file(tmp_path: Path) -> None:
    f = tmp_path / "gk.docx"
    f.write_bytes(b"x")
    manifest = Manifest(entries={"ГК": _entry("ГК", "gk.docx")})
    stats = [_stats("gk", NOW + timedelta(hours=1))]
    docs = build_documents(manifest, stats, None, base_dir=tmp_path)
    assert docs[0].status == "ingested"
    assert docs[0].chunks_count == 40


def test_stale_when_file_newer_than_db(tmp_path: Path) -> None:
    f = tmp_path / "gk.docx"
    f.write_bytes(b"x")
    old = (NOW - timedelta(days=2)).timestamp()
    os.utime(f, (old, old))
    manifest = Manifest(entries={"ГК": _entry("ГК", "gk.docx")})
    stats = [_stats("gk", NOW - timedelta(days=5))]
    docs = build_documents(manifest, stats, None, base_dir=tmp_path)
    assert docs[0].status == "stale"


def test_ingesting_overrides_other_statuses(tmp_path: Path) -> None:
    (tmp_path / "gk.docx").write_bytes(b"x")
    manifest = Manifest(entries={"ГК": _entry("ГК", "gk.docx")})
    docs = build_documents(manifest, [], "ГК", base_dir=tmp_path)
    assert docs[0].status == "ingesting"


def test_missing_file_flagged(tmp_path: Path) -> None:
    manifest = Manifest(entries={"ГК": _entry("ГК", "nope.docx")})
    docs = build_documents(manifest, [], None, base_dir=tmp_path)
    assert docs[0].file_exists is False
    assert docs[0].file_mtime is None


def test_orphaned_db_row_appended(tmp_path: Path) -> None:
    manifest = Manifest(entries={})
    docs = build_documents(manifest, [_stats("ghost", NOW)], None, base_dir=tmp_path)
    assert len(docs) == 1
    assert docs[0].status == "orphaned"
    assert docs[0].code_id is None
    assert docs[0].source_doc_id == "ghost"


def test_s3_entry_reports_size_and_mtime_from_head() -> None:
    entry = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key="corpus/gk-rf.docx",
    )
    modified = datetime(2026, 8, 1, tzinfo=UTC)
    docs = build_documents(
        Manifest(entries={entry.code_id: entry}),
        stats=[],
        active_job_code_id=None,
        s3_objects={"corpus/gk-rf.docx": ObjectInfo(size=4096, last_modified=modified)},
    )
    assert docs[0].file_exists is True
    assert docs[0].file_size == 4096
    assert docs[0].file_mtime == modified
    # `s3:` marker — the admin form posts file_path back as docx_path, and the
    # bare key would be re-read as a local path.
    assert docs[0].file_path == "s3:corpus/gk-rf.docx"


def test_s3_entry_missing_object_is_reported_as_absent() -> None:
    entry = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key="corpus/gk-rf.docx",
    )
    docs = build_documents(
        Manifest(entries={entry.code_id: entry}), stats=[], active_job_code_id=None, s3_objects={}
    )
    assert docs[0].file_exists is False
    assert docs[0].file_size is None
    assert docs[0].file_path == "s3:corpus/gk-rf.docx"
