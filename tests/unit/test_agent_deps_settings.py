import pytest

from neurolegal.agent.api import deps
from neurolegal.contracts import AgentSettings, GenerationSettings, ReviewSettings
from neurolegal.core.config import DEFAULT_REVIEW_CONCURRENCY, DEFAULT_REVIEW_MODEL


def test_get_llm_uses_persisted_settings(tmp_path, monkeypatch):
    from neurolegal.core.agent_settings import save_agent_settings

    path = tmp_path / "agent_settings.yaml"
    save_agent_settings(
        AgentSettings(model="x/custom", generation=GenerationSettings(temperature=0.7)), path
    )
    monkeypatch.setattr(deps.settings, "agent_settings_path", path)
    deps.reset_settings_caches()
    client = deps.get_llm()
    assert client._model == "x/custom"
    assert client._generation.temperature == 0.7
    deps.reset_settings_caches()


def _with_settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> AgentSettings:
    """Swap `get_agent_settings()` for a fixed in-memory `AgentSettings` for the
    duration of a test — no file round-trip needed. Clears the lru_cache-d
    functions that read it (`get_agent_settings` itself doesn't need clearing
    since it's monkeypatched away entirely)."""
    s = AgentSettings(**overrides)  # type: ignore[arg-type]
    monkeypatch.setattr(deps, "get_agent_settings", lambda: s)
    return s


def test_effective_review_model_priority_admin_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Admin setting wins over env and default.
    _with_settings(monkeypatch, review=ReviewSettings(model="a/b"))
    monkeypatch.setattr(deps.settings, "review_model", "c/d")
    assert deps.effective_review_model() == "a/b"

    # Admin setting empty — env wins.
    _with_settings(monkeypatch, review=ReviewSettings())
    assert deps.effective_review_model() == "c/d"

    # Neither set — falls back to the built-in default.
    monkeypatch.setattr(deps.settings, "review_model", None)
    assert deps.effective_review_model() == DEFAULT_REVIEW_MODEL


def test_effective_review_concurrency_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_settings(monkeypatch, review=ReviewSettings(concurrency=8))
    monkeypatch.setattr(deps.settings, "review_concurrency", 2)
    assert deps.effective_review_concurrency() == 8

    _with_settings(monkeypatch, review=ReviewSettings())
    assert deps.effective_review_concurrency() == 2

    monkeypatch.setattr(deps.settings, "review_concurrency", None)
    assert deps.effective_review_concurrency() == DEFAULT_REVIEW_CONCURRENCY


def test_get_review_llm_always_returns_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-0042: risk_review always has a model to run on — no more None fallback
    to the main chat model at the deps layer (ChatAgent still falls back to
    `self._llm` when `review_llm` isn't wired at all, e.g. in older tests)."""
    _with_settings(monkeypatch, review=ReviewSettings())
    monkeypatch.setattr(deps.settings, "review_model", None)
    deps.reset_settings_caches()
    client = deps.get_review_llm()
    assert client._model == DEFAULT_REVIEW_MODEL
    deps.reset_settings_caches()


def test_settings_hot_reload_on_file_change(tmp_path, monkeypatch):
    """T-0052: смена agent_settings.yaml подхватывается без рестарта —
    и настройки, и review-клиент пересобираются по mtime файла."""
    import os

    from neurolegal.core.agent_settings import save_agent_settings

    path = tmp_path / "agent_settings.yaml"
    save_agent_settings(AgentSettings(review=ReviewSettings(model="old/model")), path)
    monkeypatch.setattr(deps.settings, "agent_settings_path", path)
    deps.reset_settings_caches()

    assert deps.effective_review_model() == "old/model"
    first_client = deps.get_review_llm()
    assert deps.get_review_llm() is first_client  # кэш живёт, пока файл не менялся

    save_agent_settings(AgentSettings(review=ReviewSettings(model="new/model")), path)
    # mtime-гранулярность ФС может быть секундной — сдвинем явно
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 2))

    assert deps.effective_review_model() == "new/model"
    assert deps.get_review_llm() is not first_client
    assert deps.get_review_llm()._model == "new/model"
    deps.reset_settings_caches()
