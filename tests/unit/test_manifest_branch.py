from pathlib import Path

from neurolegal.rag.acquisition.manifest import ManifestEntry, load_manifest


def test_manifest_entry_accepts_branch() -> None:
    e = ManifestEntry(
        code_id="ГК-1",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс Российской Федерации (часть первая)",
        branch="Гражданское право",
        docx_path=Path("corpus/codecs/x.docx"),
    )
    assert e.branch == "Гражданское право"


def test_manifest_entry_branch_defaults_none() -> None:
    e = ManifestEntry(
        code_id="X",
        kind="codex",
        short_name="X",
        full_name="X",
        docx_path=Path("x.docx"),
    )
    assert e.branch is None


def test_real_manifest_every_entry_has_branch() -> None:
    manifest = load_manifest(Path("corpus/manifest.yaml"))
    missing = [c for c, e in manifest.entries.items() if not e.branch]
    assert missing == [], f"entries missing branch: {missing}"


def test_manifest_to_yaml_preserves_branch() -> None:
    import yaml

    from neurolegal.rag.acquisition.manifest import Manifest, manifest_to_yaml

    m = Manifest(
        entries={
            "ГК-1": ManifestEntry(
                code_id="ГК-1",
                kind="codex",
                short_name="ГК РФ",
                full_name="Гражданский кодекс РФ",
                branch="Гражданское право",
                docx_path=Path("x.docx"),
            )
        }
    )
    dumped = yaml.safe_load(manifest_to_yaml(m))
    assert dumped[0]["branch"] == "Гражданское право"
