"""Tool: list_acts — list available legal acts in the corpus."""

import json

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.agent.tools.rag_client import RagClientError

LIST_ACTS_TOOL = ToolSpec(
    name="list_acts",
    description="Показать список доступных актов (кодексов и законов) в корпусе.",
    parameters={"type": "object", "properties": {}},
)


async def handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    try:
        acts = await ctx.rag_client.list_acts()
    except RagClientError:
        return ToolOutcome(
            json.dumps({"error": "catalog unavailable"}, ensure_ascii=False), unavailable=True
        )
    payload = [{"short_name": a.short_name, "full_name": a.full_name, "kind": a.kind} for a in acts]
    return ToolOutcome(json.dumps({"acts": payload}, ensure_ascii=False))
