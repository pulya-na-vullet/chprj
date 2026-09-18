"""Tool: fetch_article — retrieve exact article text by act short-name and number."""

import json

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.chat.tools.rag_search import _format_articles
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.agent.tools.rag_client import RagClientError

FETCH_ARTICLE_TOOL = ToolSpec(
    name="fetch_article",
    description=(
        "Получить точный текст статьи по акту и номеру. Используй, когда знаешь "
        "конкретную статью, например «ст. 1477 ГК РФ»."
    ),
    parameters={
        "type": "object",
        "properties": {
            "act": {"type": "string", "description": "Короткое имя акта, напр. «ГК РФ»."},
            "number": {"type": "string", "description": "Номер статьи, напр. «1477»."},
        },
        "required": ["act", "number"],
    },
)


async def handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    act = str(arguments.get("act", "")).strip()
    number = str(arguments.get("number", "")).strip()
    if not act or not number:
        return ToolOutcome(json.dumps({"error": "act and number required"}, ensure_ascii=False))
    if ctx.acts and act not in ctx.acts:
        return ToolOutcome(json.dumps({"error": "act not in selected sources"}, ensure_ascii=False))
    try:
        articles = await ctx.rag_client.fetch_article(act, number)
    except RagClientError:
        return ToolOutcome(
            json.dumps({"error": "lookup unavailable"}, ensure_ascii=False), unavailable=True
        )
    if not articles:
        return ToolOutcome(json.dumps({"articles": []}, ensure_ascii=False))
    return ToolOutcome(_format_articles(articles), articles=articles)
