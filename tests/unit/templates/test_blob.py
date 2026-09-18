"""Key guard + prefix helpers + in-memory fake."""

import pytest

from neurolegal.templates.store.blob import (
    InMemoryTemplatesBlobStore,
    TemplateBlobMissingError,
    UnsafeTemplateKeyError,
    normalize_prefix,
    safe_template_key,
    template_key,
)


def test_normalize_prefix() -> None:
    assert normalize_prefix("templates/") == "templates/"
    assert normalize_prefix("templates") == "templates/"
    assert normalize_prefix("") == ""


def test_template_key() -> None:
    assert template_key("arenda-kvartiry", "templates/") == "templates/arenda-kvartiry.docx"
    assert template_key("arenda", "tpl") == "tpl/arenda.docx"


def test_safe_template_key_accepts_keys_inside_prefix() -> None:
    assert safe_template_key("templates/arenda.docx", "templates/") == "templates/arenda.docx"
    # префикс без слэша нормализуется так же, как при построении ключа
    assert safe_template_key("templates/a/b.docx", "templates") == "templates/a/b.docx"


@pytest.mark.parametrize(
    "raw",
    [
        "owner/u1/doc/original.docx",  # чужой префикс общего бакета
        "corpus/gk-1.docx",  # корпус RAG
        "templates/",  # ровно префикс, не файл
        "templates/evil.pdf",  # не .docx
        "templates/../owner/u1/doc/original.docx",  # обход через ..
        "/templates/arenda.docx",  # абсолютный ключ
    ],
)
def test_safe_template_key_rejects(raw: str) -> None:
    with pytest.raises(UnsafeTemplateKeyError):
        safe_template_key(raw, "templates/")


async def test_in_memory_store_roundtrip() -> None:
    store = InMemoryTemplatesBlobStore()
    await store.put("templates/a.docx", b"bytes")
    assert await store.get("templates/a.docx") == b"bytes"
    await store.delete("templates/a.docx")
    with pytest.raises(TemplateBlobMissingError):
        await store.get("templates/a.docx")
