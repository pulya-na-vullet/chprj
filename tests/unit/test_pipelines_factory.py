from pathlib import Path
from unittest.mock import AsyncMock

from neurolegal.rag.acquisition.docx import DocxAcquirer
from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry
from neurolegal.rag.acquisition.pravo_gov import PravoGovAcquirer
from neurolegal.rag.parsing.docx import DocxParser
from neurolegal.rag.parsing.pravo_gov_html import PravoGovHTMLParser
from neurolegal.rag.pipelines.factory import build_pipeline


def _manifest(tmp_path: Path) -> Manifest:
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"PK\x03\x04")
    return Manifest(
        entries={
            "ГК-1": ManifestEntry(
                code_id="ГК-1",
                kind="codex",
                short_name="ГК РФ",
                full_name="…",
                docx_path=docx,
            )
        }
    )


def test_build_pipeline_docx(tmp_path: Path) -> None:
    p = build_pipeline(
        "docx",
        manifest=_manifest(tmp_path),
        embedder=AsyncMock(),
        session_factory=lambda: AsyncMock(),  # type: ignore[arg-type, return-value]
    )
    assert isinstance(p._acquirer, DocxAcquirer)
    assert isinstance(p._parser, DocxParser)


def test_build_pipeline_docx_without_store_has_no_s3_branch(tmp_path: Path) -> None:
    p = build_pipeline(
        "docx",
        manifest=_manifest(tmp_path),
        embedder=AsyncMock(),
        session_factory=lambda: AsyncMock(),  # type: ignore[arg-type, return-value]
    )
    assert isinstance(p._acquirer, DocxAcquirer)
    assert p._acquirer._s3 is None


def test_build_pipeline_pravo(tmp_path: Path) -> None:
    p = build_pipeline(
        "pravo",
        manifest=_manifest(tmp_path),
        embedder=AsyncMock(),
        session_factory=lambda: AsyncMock(),  # type: ignore[arg-type, return-value]
    )
    assert isinstance(p._acquirer, PravoGovAcquirer)
    assert isinstance(p._parser, PravoGovHTMLParser)
