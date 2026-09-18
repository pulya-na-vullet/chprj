from neurolegal.documents.store.blob import InMemoryBlobStore


async def test_in_memory_put_get_delete():
    store = InMemoryBlobStore()
    await store.put("k1", b"hello", "text/plain")
    assert store.objects["k1"] == b"hello"
    url = await store.presigned_url("k1")
    assert "k1" in url
    await store.delete("k1")
    assert "k1" not in store.objects


async def test_presigned_url_missing_key_still_returns_str():
    store = InMemoryBlobStore()
    url = await store.presigned_url("absent")
    assert isinstance(url, str)
