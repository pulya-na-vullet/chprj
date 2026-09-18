from neurolegal.agent.chat.tools.base import ToolOutcome


def test_tool_outcome_defaults() -> None:
    o = ToolOutcome(tool_result="{}")
    assert o.articles == []
    assert o.web_sources == []
    assert o.unavailable is False
