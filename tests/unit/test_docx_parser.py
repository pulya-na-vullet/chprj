from datetime import UTC, datetime
from pathlib import Path

import pytest

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.local_docx import LocalDocxAcquirer
from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry
from neurolegal.rag.parsing.docx import DocxParseError, DocxParser

CORPUS = Path(__file__).parent.parent.parent / "corpus"


@pytest.fixture
def gk1_manifest_entry() -> ManifestEntry:
    return ManifestEntry(
        code_id="ГК-1",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс Российской Федерации (часть первая)",
        redaction="31.07.2025",
        docx_path=CORPUS
        / "codecs"
        / "Гражданский кодекс Российской Федерации (часть первая)  от 3.docx",
    )


@pytest.fixture
def fz44_manifest_entry() -> ManifestEntry:
    return ManifestEntry(
        code_id="ФЗ-44",
        kind="federal_law",
        short_name="44-ФЗ",
        full_name="О контрактной системе…",
        redaction="28.12.2025",
        docx_path=CORPUS
        / "federal_law"
        / "Федеральный закон от 05.04.2013 N 44-ФЗ (ред. от 28.12.2025).docx",
    )


@pytest.mark.skipif(
    not (
        CORPUS / "codecs" / "Гражданский кодекс Российской Федерации (часть первая)  от 3.docx"
    ).exists(),
    reason="ГК-1 docx not in repo",
)
async def test_parse_real_gk1(gk1_manifest_entry: ManifestEntry) -> None:
    manifest = Manifest(entries={"ГК-1": gk1_manifest_entry})
    parser = DocxParser(manifest)
    acquirer = LocalDocxAcquirer(manifest)
    raw = await acquirer.fetch("ГК-1")

    doc = parser.parse(raw)

    assert doc.act.kind == "codex"
    assert doc.act.short_name == "ГК РФ"
    assert doc.act.source_doc_id == "gk-1"
    # ГК-1 has > 430 articles
    assert len(doc.articles) > 430
    # there must be at least one section "Раздел"
    assert any(n.type == "section" for n in doc.structure_nodes)
    # find article 421 ("Свобода договора")
    art421 = next((a for a in doc.articles if a.number == "421"), None)
    assert art421 is not None
    assert art421.title is not None and "вобода" in art421.title.lower()
    assert art421.points is not None
    assert len(art421.points) >= 4


@pytest.mark.skipif(
    not (
        CORPUS / "federal_law" / "Федеральный закон от 05.04.2013 N 44-ФЗ (ред. от 28.12.2025).docx"
    ).exists(),
    reason="ФЗ-44 docx not in repo",
)
async def test_parse_real_fz44(fz44_manifest_entry: ManifestEntry) -> None:
    manifest = Manifest(entries={"ФЗ-44": fz44_manifest_entry})
    parser = DocxParser(manifest)
    acquirer = LocalDocxAcquirer(manifest)
    raw = await acquirer.fetch("ФЗ-44")

    doc = parser.parse(raw)

    assert doc.act.kind == "federal_law"
    assert len(doc.articles) > 50  # 44-ФЗ has ~100 articles


def test_parse_raises_when_no_articles(tmp_path: Path) -> None:
    """Synthetic minimal docx with only boilerplate → DocxParseError."""
    from docx import Document

    d = Document()
    d.add_paragraph("Документ предоставлен КонсультантПлюс")
    d.add_paragraph("www.consultant.ru")
    docx_path = tmp_path / "empty.docx"
    d.save(str(docx_path))

    manifest = Manifest(
        entries={
            "X": ManifestEntry(
                code_id="X",
                kind="codex",
                short_name="X",
                full_name="X",
                docx_path=docx_path,
            )
        }
    )
    parser = DocxParser(manifest)
    raw = RawDocument(
        source="local-docx",
        source_doc_id="x",
        fetched_at=datetime.now(UTC),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body_bytes=docx_path.read_bytes(),
    )
    with pytest.raises(DocxParseError, match="no articles"):
        parser.parse(raw)


def test_parse_article_with_hyphen_suffix(tmp_path: Path) -> None:
    """Articles inserted by amendment use 'N.M.K-1' notation (КоАП ст. 14.1.1-1)."""
    from docx import Document

    d = Document()
    d.add_paragraph("Глава 14. ПРАВОНАРУШЕНИЯ В ПРЕДПРИНИМАТЕЛЬСТВЕ")
    d.add_paragraph("Статья 14.1.1. Незаконные организация и проведение азартных игр")
    d.add_paragraph("1. Организация азартных игр…")
    d.add_paragraph("Статья 14.1.1-1. Нарушение организаторами азартных игр требований")
    d.add_paragraph("1. Прием организатором азартной игры ставок…")
    docx_path = tmp_path / "hyphen.docx"
    d.save(str(docx_path))

    manifest = Manifest(
        entries={
            "X": ManifestEntry(
                code_id="X",
                kind="codex",
                short_name="X",
                full_name="X",
                docx_path=docx_path,
            )
        }
    )
    parser = DocxParser(manifest)
    raw = RawDocument(
        source="local-docx",
        source_doc_id="x",
        fetched_at=datetime.now(UTC),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body_bytes=docx_path.read_bytes(),
    )
    doc = parser.parse(raw)
    nums = [a.number for a in doc.articles]
    assert nums == ["14.1.1", "14.1.1-1"]
    assert doc.articles[1].title is not None
    assert doc.articles[1].title.startswith("Нарушение")


def test_parse_drops_standalone_tombstones(tmp_path: Path) -> None:
    """Repealed articles without a replacement (e.g. КоАП ст. 18.1 'Утратила
    силу') should be dropped — they have empty body and would pollute the
    chunk index with embeddings of empty strings.
    """
    from docx import Document

    d = Document()
    d.add_paragraph("Глава 1. ОБЩИЕ ПОЛОЖЕНИЯ")
    d.add_paragraph("Статья 1. Предмет регулирования")
    d.add_paragraph("Настоящий закон регулирует отношения…")
    d.add_paragraph("Статья 1.1. Утратила силу с 1 января 2020 года.")
    d.add_paragraph("Статья 2. Сфера действия")
    d.add_paragraph("Закон распространяется на…")
    docx_path = tmp_path / "tombstone.docx"
    d.save(str(docx_path))

    manifest = Manifest(
        entries={
            "X": ManifestEntry(
                code_id="X",
                kind="codex",
                short_name="X",
                full_name="X",
                docx_path=docx_path,
            )
        }
    )
    parser = DocxParser(manifest)
    raw = RawDocument(
        source="local-docx",
        source_doc_id="x",
        fetched_at=datetime.now(UTC),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body_bytes=docx_path.read_bytes(),
    )
    doc = parser.parse(raw)
    nums = [a.number for a in doc.articles]
    assert nums == ["1", "2"]
    assert all(a.full_text.strip() for a in doc.articles)


def test_parse_dedupes_tombstone_when_number_reused(tmp_path: Path) -> None:
    """Russian codices sometimes carry an 'Утратила силу' tombstone with the
    same number as a new article in a later chapter (e.g. БК ст. 242.1). The
    tombstone has empty body; the parser must keep the non-empty entry to
    avoid colliding on uq_articles_act_number.
    """
    from docx import Document

    d = Document()
    d.add_paragraph("Глава 1. ОБЩИЕ ПОЛОЖЕНИЯ")
    d.add_paragraph("Статья 242.1. Утратила силу с 1 января 2008 года.")
    d.add_paragraph("Глава 2. БЮДЖЕТНЫЕ ПОЛНОМОЧИЯ")
    d.add_paragraph("Статья 242.1. Общие положения")
    d.add_paragraph("Исполнение судебных актов производится в соответствии с настоящей главой.")
    docx_path = tmp_path / "dup.docx"
    d.save(str(docx_path))

    manifest = Manifest(
        entries={
            "X": ManifestEntry(
                code_id="X",
                kind="codex",
                short_name="X",
                full_name="X",
                docx_path=docx_path,
            )
        }
    )
    parser = DocxParser(manifest)
    raw = RawDocument(
        source="local-docx",
        source_doc_id="x",
        fetched_at=datetime.now(UTC),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body_bytes=docx_path.read_bytes(),
    )
    doc = parser.parse(raw)
    arts = [a for a in doc.articles if a.number == "242.1"]
    assert len(arts) == 1
    assert arts[0].title == "Общие положения"
    assert "Исполнение" in arts[0].full_text


def test_parse_skips_boilerplate_paragraphs(tmp_path: Path) -> None:
    """КонсультантПлюс header lines do not appear in any article body."""
    from docx import Document

    d = Document()
    d.add_paragraph("Документ предоставлен КонсультантПлюс")
    d.add_paragraph("www.consultant.ru")
    d.add_paragraph("Дата сохранения: 10.05.2026")
    d.add_paragraph("Глава 1. ОБЩИЕ ПОЛОЖЕНИЯ")
    d.add_paragraph("Статья 1. Предмет регулирования")
    d.add_paragraph("1. Настоящий закон регулирует отношения...")
    docx_path = tmp_path / "synth.docx"
    d.save(str(docx_path))

    manifest = Manifest(
        entries={
            "X": ManifestEntry(
                code_id="X",
                kind="codex",
                short_name="X",
                full_name="X",
                docx_path=docx_path,
            )
        }
    )
    parser = DocxParser(manifest)
    raw = RawDocument(
        source="local-docx",
        source_doc_id="x",
        fetched_at=datetime.now(UTC),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body_bytes=docx_path.read_bytes(),
    )
    doc = parser.parse(raw)
    assert len(doc.articles) == 1
    assert "КонсультантПлюс" not in doc.articles[0].full_text
    assert "www.consultant.ru" not in doc.articles[0].full_text
