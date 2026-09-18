import pytest

from neurolegal.core.config import Settings


def test_llm_model_default() -> None:
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.llm_model == "qwen/qwen3.6-flash"


def test_llm_model_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_LLM_MODEL", "anthropic/claude-3.5-sonnet")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.llm_model == "anthropic/claude-3.5-sonnet"


def test_settings_default_rag_min_score() -> None:
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.rag_min_score == 0.0


def test_settings_reads_rag_min_score_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_RAG_MIN_SCORE", "0.07")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.rag_min_score == 0.07


def test_settings_rejects_negative_rag_min_score(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("NEUROLEGAL_RAG_MIN_SCORE", "-0.1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")


def test_settings_default_rag_base_url() -> None:
    """In dev the agent talks to RAG on localhost:8001 — keep that default."""
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.rag_base_url == "http://127.0.0.1:8001"


def test_settings_reads_rag_base_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_RAG_BASE_URL", "https://rag.staging.example")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.rag_base_url == "https://rag.staging.example"


def test_admin_enabled_default_true_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from neurolegal.core.config import Settings

    monkeypatch.delenv("NEUROLEGAL_ADMIN_ENABLED", raising=False)
    assert Settings().admin_enabled is True

    monkeypatch.setenv("NEUROLEGAL_ADMIN_ENABLED", "0")
    assert Settings().admin_enabled is False


def test_tavily_api_key_default_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest surfaces a developer's .env.local into os.environ, so clear the
    # var explicitly to assert the built-in default rather than the local config.
    monkeypatch.delenv("NEUROLEGAL_TAVILY_API_KEY", raising=False)
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.tavily_api_key is None


def test_tavily_api_key_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_TAVILY_API_KEY", "tvly-testkey123")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.tavily_api_key == "tvly-testkey123"


def test_playbooks_dir_default() -> None:
    from pathlib import Path

    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.playbooks_dir == Path("playbooks")


def test_playbooks_dir_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("NEUROLEGAL_PLAYBOOKS_DIR", "/data/playbooks")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.playbooks_dir == Path("/data/playbooks")


def test_review_model_default_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEUROLEGAL_REVIEW_MODEL", raising=False)
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.review_model is None


def test_review_model_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_REVIEW_MODEL", "anthropic/claude-3.5-sonnet")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.review_model == "anthropic/claude-3.5-sonnet"


def test_review_concurrency_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_REVIEW_CONCURRENCY", "8")
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.review_concurrency == 8


def test_review_concurrency_default_unset() -> None:
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    assert s.review_concurrency is None


def test_review_concurrency_rejects_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Semaphore(0) in ReviewEngine deadlocks every worker forever — reject
    at config load instead of failing silently at review time."""
    from pydantic import ValidationError

    monkeypatch.setenv("NEUROLEGAL_REVIEW_CONCURRENCY", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")


def test_review_concurrency_rejects_above_twelve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors contracts.agent_settings.ReviewSettings.concurrency's le=12 —
    keep the env-var and admin-setting validation symmetric."""
    from pydantic import ValidationError

    monkeypatch.setenv("NEUROLEGAL_REVIEW_CONCURRENCY", "13")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")


def test_to_asyncpg_url_passes_clean_local_url_through() -> None:
    """Regression: function must work for plain local URLs, not only Neon-style.

    The Neon URL had `sslmode` and `channel_binding` query params that asyncpg
    rejects; this function strips them. A clean URL (no such params) must
    just acquire the `+asyncpg` driver tag and survive otherwise unchanged.
    """
    from neurolegal.core.config import to_asyncpg_url

    src = "postgresql://neurolegal:neurolegal@127.0.0.1:5432/neurolegal"
    assert (
        to_asyncpg_url(src)
        == "postgresql+asyncpg://neurolegal:neurolegal@127.0.0.1:5432/neurolegal"
    )
