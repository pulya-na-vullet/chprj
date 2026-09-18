import pytest
from pydantic import ValidationError

from neurolegal.contracts import AgentSettings, GenerationSettings, ReviewSettings


def test_agent_settings_defaults():
    s = AgentSettings()
    assert s.model == "qwen/qwen3.6-flash"
    assert s.generation.temperature is None
    assert s.behavior.max_tool_iterations == 8
    assert s.behavior.tool_choice == "auto"
    assert s.tools.rag_search.enabled is True
    assert s.tools.rag_search.limit == 8


def test_agent_settings_round_trip():
    s = AgentSettings(model="x/y", generation=GenerationSettings(temperature=0.3, seed=7))
    again = AgentSettings.model_validate(s.model_dump())
    assert again.generation.temperature == 0.3
    assert again.generation.seed == 7


def test_review_settings_defaults() -> None:
    s = AgentSettings()
    assert s.review.model is None
    assert s.review.concurrency is None


def test_review_settings_roundtrip() -> None:
    s = AgentSettings(review=ReviewSettings(model="openai/gpt-4o-mini", concurrency=6))
    restored = AgentSettings.model_validate(s.model_dump())
    assert restored.review.model == "openai/gpt-4o-mini"
    assert restored.review.concurrency == 6


def test_review_settings_concurrency_bounds() -> None:
    with pytest.raises(ValidationError):
        ReviewSettings(concurrency=0)
    with pytest.raises(ValidationError):
        ReviewSettings(concurrency=13)
