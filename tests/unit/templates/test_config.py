from neurolegal.templates.config import TemplatesSettings


def test_defaults_and_env(monkeypatch):
    monkeypatch.delenv("NEUROLEGAL_TEMPLATES_S3_PREFIX", raising=False)
    assert TemplatesSettings().templates_s3_prefix == "templates/"
    monkeypatch.setenv("NEUROLEGAL_TEMPLATES_S3_PREFIX", "tpl/")
    monkeypatch.setenv("NEUROLEGAL_S3_BUCKET", "other-bucket")
    s = TemplatesSettings()
    assert s.templates_s3_prefix == "tpl/"
    assert s.s3_bucket == "other-bucket"
