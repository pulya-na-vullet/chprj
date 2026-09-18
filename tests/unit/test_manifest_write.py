"""save_manifest: атомарная перезапись manifest.yaml + round-trip."""

from pathlib import Path

from neurolegal.rag.acquisition.manifest import (
    Manifest,
    ManifestEntry,
    load_manifest,
    save_manifest,
)


def _manifest() -> Manifest:
    entries = {
        "ГК-1": ManifestEntry(
            code_id="ГК-1",
            kind="codex",
            short_name="ГК РФ",
            full_name="Гражданский кодекс (часть первая)",
            docx_path=Path("corpus/codecs/gk1.docx"),
        ),
        "44-ФЗ": ManifestEntry(
            code_id="44-ФЗ",
            kind="federal_law",
            short_name="44-ФЗ",
            full_name="О контрактной системе",
            redaction="ред. от 28.12.2025",
            docx_path=Path("corpus/federal_law/44fz.docx"),
        ),
    }
    return Manifest(entries=entries)


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    original = _manifest()
    save_manifest(original, path)
    loaded = load_manifest(path)
    assert loaded == original


def test_save_preserves_entry_order(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    save_manifest(_manifest(), path)
    text = path.read_text("utf-8")
    assert text.index("ГК-1") < text.index("44-ФЗ")


def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    save_manifest(_manifest(), path)
    assert path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_optional_fields_omitted_when_none(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    save_manifest(_manifest(), path)
    text = path.read_text("utf-8")
    # ГК-1 has no redaction → no "redaction:" line for it; 44-ФЗ has one.
    assert text.count("redaction:") == 1
    assert "pravo_url" not in text
