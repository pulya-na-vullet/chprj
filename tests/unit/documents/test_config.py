from neurolegal.documents.config import DocumentsSettings


def test_defaults_and_env(monkeypatch):
    monkeypatch.setenv("NEUROLEGAL_S3_BUCKET", "docs-bucket")
    monkeypatch.setenv("NEUROLEGAL_TESSDATA_PATH", "/opt/tessdata")
    s = DocumentsSettings()
    assert s.s3_bucket == "docs-bucket"
    assert str(s.tessdata_path) == "/opt/tessdata"
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert s.allowed_suffixes == frozenset({".docx", ".pdf"})
    # base_url has a sane local default
    assert s.documents_base_url == "http://127.0.0.1:8002"
    # T-0017: summary_model defaults to openai/gpt-4o-mini
    monkeypatch.delenv("NEUROLEGAL_SUMMARY_MODEL", raising=False)
    assert DocumentsSettings().summary_model == "openai/gpt-4o-mini"
