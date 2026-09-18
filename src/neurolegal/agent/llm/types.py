"""LLM-facing data types: chat messages, tool specs, and stream events.

These are provider-neutral; OpenRouter-specific shaping is done via the
``to_openrouter`` methods.
"""

from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    role: Role
    content: str | None = None
    tool_calls: list[dict[str, object]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_openrouter(self) -> dict[str, object]:
        msg: dict[str, object] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls is not None:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, object]

    def to_openrouter(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ReasoningChunk:
    """A streamed fragment of the model's reasoning (thinking) trace.

    Reasoning models emit these before the visible answer. It is shown to the
    user as an ephemeral "thinking" indicator and never stored as the answer.
    """

    text: str


@dataclass
class TextChunk:
    """A streamed fragment of the model's final answer text."""

    text: str


@dataclass
class ToolCallRequest:
    """A fully-accumulated tool call the model wants the agent to execute."""

    id: str
    name: str
    arguments: dict[str, object]


LLMEvent = ReasoningChunk | TextChunk | ToolCallRequest
