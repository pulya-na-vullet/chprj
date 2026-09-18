from neurolegal.agent.llm.client import OpenRouterChatClient
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.contracts import GenerationSettings


def _tool() -> ToolSpec:
    return ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})


def test_build_payload_includes_set_generation_fields() -> None:
    client = OpenRouterChatClient(
        api_key="k",
        model="a/b",
        generation=GenerationSettings(temperature=0.3, max_tokens=512, reasoning_effort="low"),
    )
    payload = client._build_payload([], [])
    assert payload["model"] == "a/b"
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 512
    assert payload["reasoning_effort"] == "low"
    assert "top_p" not in payload  # None omitted


def test_build_payload_tool_choice_only_with_tools() -> None:
    client = OpenRouterChatClient(api_key="k", model="a/b", tool_choice="required")
    assert "tool_choice" not in client._build_payload([], [])
    with_tools = client._build_payload([], [_tool()])
    assert with_tools["tool_choice"] == "required"
