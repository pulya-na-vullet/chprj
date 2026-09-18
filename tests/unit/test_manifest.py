from pathlib import Path

import pytest
from pydantic import ValidationError

from neurolegal.rag.acquisition.manifest import (
    Manifest,
    ManifestEntry,
    get_entry,
    load_manifest,
    manifest_to_yaml,
    slugify_code_id,
)


def test_slugify_code_id_codex_simple() -> None:
    assert slugify_code_id("УК") == "uk"


def test_slugify_code_id_codex_multipart() -> None:
    assert slugify_code_id("ГК-1") == "gk-1"
    assert slugify_code_id("НК-2") == "nk-2"


def test_slugify_code_id_federal_law() -> None:
    assert slugify_code_id("ФЗ-44") == "fz-44"


def test_slugify_code_id_eaeu() -> None:
    assert slugify_code_id("ТК-ЕАЭС") == "tk-eaes"


def test_slugify_code_id_specials() -> None:
    assert slugify_code_id("КоАП") == "koap"
    assert slugify_code_id("ВзК") == "vzk"
    assert slugify_code_id("ГрК") == "grk"
    assert slugify_code_id("ЗПП") == "zpp"


def test_manifest_entry_requires_locator() -> None:
    with pytest.raises(ValueError, match="need docx_path, docx_s3_key or pravo_url"):
        ManifestEntry(
            code_id="ГК-1",
            kind="codex",
            short_name="ГК РФ",
            full_name="…",
        )


def test_manifest_entry_with_docx_path(tmp_path: Path) -> None:
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"fake")
    entry = ManifestEntry(
        code_id="ГК-1",
        kind="codex",
        short_name="ГК РФ",
        full_name="…",
        docx_path=docx,
    )
    assert entry.source_doc_id == "gk-1"
    assert entry.docx_path == docx


def test_load_manifest_from_yaml(tmp_path: Path) -> None:
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"fake")
    yaml_path = tmp_path / "manifest.yaml"
    yaml_path.write_text(
        f"""
- code_id: ГК-1
  kind: codex
  short_name: ГК РФ
  full_name: Гражданский кодекс (часть первая)
  redaction: "31.07.2025"
  docx_path: {docx}
- code_id: ФЗ-44
  kind: federal_law
  short_name: 44-ФЗ
  full_name: О контрактной системе
  docx_path: {docx}
""",
        encoding="utf-8",
    )
    manifest = load_manifest(yaml_path)
    assert set(manifest.entries.keys()) == {"ГК-1", "ФЗ-44"}
    assert manifest.entries["ГК-1"].kind == "codex"
    assert manifest.entries["ФЗ-44"].kind == "federal_law"


def test_load_manifest_rejects_non_list_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "manifest.yaml"
    yaml_path.write_text("foo: bar\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a YAML list"):
        load_manifest(yaml_path)


def test_get_entry_unknown_raises(tmp_path: Path) -> None:
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"fake")
    manifest = Manifest(
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
    with pytest.raises(KeyError):
        get_entry("UNKNOWN", manifest)


def test_entry_accepts_s3_key_as_the_only_locator() -> None:
    entry = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key="corpus/gk-rf.docx",
    )
    assert entry.docx_s3_key == "corpus/gk-rf.docx"


def test_entry_without_any_locator_still_rejected() -> None:
    with pytest.raises(ValidationError):
        ManifestEntry(code_id="X", kind="codex", short_name="X", full_name="X")


def test_yaml_roundtrip_keeps_s3_key() -> None:
    entry = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key="corpus/gk-rf.docx",
    )
    text = manifest_to_yaml(Manifest(entries={entry.code_id: entry}))
    assert "docx_s3_key: corpus/gk-rf.docx" in text
