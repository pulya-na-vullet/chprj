from pathlib import Path

import pytest

from neurolegal.rag.acquisition.corpus_store import InMemoryCorpusStore
from neurolegal.rag.acquisition.docx import DocxAcquirer
from neurolegal.rag.acquisition.local_docx import LocalDocxAcquirer
from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry
from neurolegal.rag.acquisition.s3_docx import S3DocxAcquirer


def _manifest(**entry_kwargs: object) -> Manifest:
    entry = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        **entry_kwargs,  # type: ignore[arg-type]
    )
    return Manifest(entries={entry.code_id: entry})


async def test_s3_acquirer_fetches_bytes_by_key() -> None:
    store = InMemoryCorpusStore()
    await store.put("corpus/gk-rf.docx", b"PK\x03\x04payload")
    acquirer = S3DocxAcquirer(_manifest(docx_s3_key="corpus/gk-rf.docx"), store)

    raw = await acquirer.fetch("ГК РФ")

    assert raw.body_bytes == b"PK\x03\x04payload"
    assert raw.source == "s3-docx"
    # slugify_code_id() drops spaces silently rather than hyphenating them
    # (see corpus_store.corpus_key's docstring) — "ГК РФ" -> "gkrf".
    assert raw.source_doc_id == "gkrf"


async def test_s3_acquirer_without_key_raises() -> None:
    acquirer = S3DocxAcquirer(_manifest(docx_path="corpus/codecs/gk.docx"), InMemoryCorpusStore())
    with pytest.raises(FileNotFoundError, match="no docx_s3_key"):
        await acquirer.fetch("ГК РФ")


async def test_dispatcher_prefers_s3_when_key_present() -> None:
    store = InMemoryCorpusStore()
    await store.put("corpus/gk-rf.docx", b"from-s3")
    manifest = _manifest(docx_s3_key="corpus/gk-rf.docx")
    acquirer = DocxAcquirer(
        manifest,
        local=LocalDocxAcquirer(manifest),
        s3=S3DocxAcquirer(manifest, store),
    )

    raw = await acquirer.fetch("ГК РФ")

    assert raw.body_bytes == b"from-s3"


async def test_dispatcher_falls_back_to_local(tmp_path: Path) -> None:
    path = tmp_path / "gk.docx"
    path.write_bytes(b"from-disk")
    manifest = _manifest(docx_path=path)
    acquirer = DocxAcquirer(manifest, local=LocalDocxAcquirer(manifest), s3=None)

    raw = await acquirer.fetch("ГК РФ")

    assert raw.body_bytes == b"from-disk"


async def test_dispatcher_without_store_but_with_key_explains_itself() -> None:
    manifest = _manifest(docx_s3_key="corpus/gk-rf.docx")
    acquirer = DocxAcquirer(manifest, local=LocalDocxAcquirer(manifest), s3=None)
    with pytest.raises(RuntimeError, match="S3 credentials"):
        await acquirer.fetch("ГК РФ")
