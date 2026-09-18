from neurolegal.core.config import Settings


def test_documents_base_url_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.delenv("NEUROLEGAL_DOCUMENTS_BASE_URL", raising=False)
    assert Settings().documents_base_url == "http://127.0.0.1:8002"


def test_documents_base_url_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("NEUROLEGAL_DOCUMENTS_BASE_URL", "http://hub:9000")
    assert Settings().documents_base_url == "http://hub:9000"
