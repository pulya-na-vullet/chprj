from pathlib import Path

import pytest

from neurolegal.rag.acquisition.local_docx import LocalDocxAcquirer
from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry


@pytest.fixture
def manifest_with_docx(tmp_path: Path) -> tuple[Manifest, Path]:
    docx = tmp_path / "fake.docx"
    docx.write_bytes(b"PK\x03\x04fake-docx-bytes")
    m = Manifest(
        entries={
            "ГК-1": ManifestEntry(
                code_id="ГК-1",
                kind="codex",
                short_name="ГК РФ",
                full_name="…",
                docx_path=docx,
            ),
            "ФЗ-44": ManifestEntry(
                code_id="ФЗ-44",
                kind="federal_law",
                short_name="44-ФЗ",
                full_name="…",
                pravo_url="https://example.com/fz44.html",
            ),
        }
    )
    return m, docx


async def test_fetch_returns_raw_document(manifest_with_docx: tuple[Manifest, Path]) -> None:
    manifest, docx = manifest_with_docx
    acq = LocalDocxAcquirer(manifest)
    raw = await acq.fetch("ГК-1")
    assert raw.source == "local-docx"
    assert raw.source_doc_id == "gk-1"
    assert raw.body_bytes == docx.read_bytes()
    assert "wordprocessingml" in raw.content_type


async def test_fetch_unknown_code_raises(manifest_with_docx: tuple[Manifest, Path]) -> None:
    manifest, _ = manifest_with_docx
    acq = LocalDocxAcquirer(manifest)
    with pytest.raises(KeyError):
        await acq.fetch("UNKNOWN")


async def test_fetch_no_docx_path_raises(manifest_with_docx: tuple[Manifest, Path]) -> None:
    manifest, _ = manifest_with_docx
    acq = LocalDocxAcquirer(manifest)
    with pytest.raises(FileNotFoundError, match="no docx_path"):
        await acq.fetch("ФЗ-44")
