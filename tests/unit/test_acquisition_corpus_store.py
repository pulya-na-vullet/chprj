from datetime import UTC

import pytest

from neurolegal.core.config import Settings
from neurolegal.rag.acquisition.corpus_store import (
    InMemoryCorpusStore,
    MissingS3CredentialsError,
    ObjectInfo,
    build_corpus_store,
    build_corpus_store_or_none,
    corpus_key,
)
from neurolegal.rag.acquisition.manifest import ManifestEntry


async def test_in_memory_roundtrip() -> None:
    store = InMemoryCorpusStore()
    await store.put("corpus/gk-rf.docx", b"PK\x03\x04")
    assert await store.get("corpus/gk-rf.docx") == b"PK\x03\x04"


async def test_head_returns_size_and_mtime() -> None:
    store = InMemoryCorpusStore()
    await store.put("corpus/gk-rf.docx", b"1234")
    info = await store.head("corpus/gk-rf.docx")
    assert isinstance(info, ObjectInfo)
    assert info.size == 4
    assert info.last_modified.tzinfo is UTC


async def test_head_missing_key_returns_none() -> None:
    assert await InMemoryCorpusStore().head("nope.docx") is None


async def test_delete_is_idempotent() -> None:
    store = InMemoryCorpusStore()
    await store.delete("nope.docx")
    assert store.objects == {}


async def test_get_missing_key_raises() -> None:
    with pytest.raises(FileNotFoundError):
        await InMemoryCorpusStore().get("nope.docx")


def test_corpus_key_uses_prefix_and_slug() -> None:
    assert corpus_key("ГК-1", "corpus/") == "corpus/gk-1.docx"


def test_corpus_key_stem_matches_act_identity() -> None:
    """Ключ объекта обязан быть равен source_doc_id акта.

    Иначе объект в бакете не сопоставить акту в БД: идентичность акта —
    slugify_code_id(code_id), поэтому собственная нормализация в corpus_key
    разводила бы их для code_id, содержащих пробелы.
    """
    entry = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key="corpus/x.docx",
    )
    assert corpus_key(entry.code_id, "corpus/") == f"corpus/{entry.source_doc_id}.docx"


def test_corpus_key_normalizes_prefix_without_trailing_slash() -> None:
    """NEUROLEGAL_CORPUS_S3_PREFIX=corpus must not glue into `corpusgk-1.docx`."""
    assert corpus_key("ГК-1", "corpus") == "corpus/gk-1.docx"


def test_corpus_key_keeps_empty_prefix_empty() -> None:
    assert corpus_key("ГК-1", "") == "gk-1.docx"


async def test_list_prefix_filters_by_prefix() -> None:
    store = InMemoryCorpusStore()
    await store.put("corpus/gk-1.docx", b"1234")
    await store.put("owner/u1/d1/original.pdf", b"x")
    listing = await store.list_prefix("corpus/")
    assert list(listing) == ["corpus/gk-1.docx"]
    assert listing["corpus/gk-1.docx"].size == 4


async def test_list_prefix_empty_store_is_empty() -> None:
    assert await InMemoryCorpusStore().list_prefix("corpus/") == {}


def test_build_corpus_store_without_credentials_raises() -> None:
    s = Settings(DATABASE_URL="postgresql://x/y", NEUROLEGAL_S3_ACCESS_KEY=None)
    with pytest.raises(MissingS3CredentialsError, match="S3 credentials missing"):
        build_corpus_store(s)


def test_build_corpus_store_or_none_without_credentials_returns_none() -> None:
    s = Settings(DATABASE_URL="postgresql://x/y", NEUROLEGAL_S3_ACCESS_KEY=None)
    assert build_corpus_store_or_none(s) is None


def test_build_corpus_store_or_none_with_credentials_returns_store() -> None:
    s = Settings(
        DATABASE_URL="postgresql://x/y",
        NEUROLEGAL_S3_ACCESS_KEY="ak",
        NEUROLEGAL_S3_SECRET_KEY="sk",
    )
    assert build_corpus_store_or_none(s) is not None
