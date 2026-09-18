"""The `rag_search` tool: spec + registry handler."""

import json

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.agent.tools.rag_client import RagClientError
from neurolegal.contracts import SEARCH_QUERY_MAX_CHARS, SearchedArticle

RAG_SEARCH_TOOL = ToolSpec(
    name="rag_search",
    description=(
        "Поиск релевантных статей в корпусе законодательства РФ. Используй для "
        "любого вопроса о праве — отвечать можно только по статьям, которые "
        "вернул этот инструмент."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "maxLength": SEARCH_QUERY_MAX_CHARS,
                "description": "Краткий поисковый запрос на русском языке.",
            },
        },
        "required": ["query"],
    },
)


def _format_articles(articles: list[SearchedArticle]) -> str:
    payload = [
        {
            "act": a.act_short_name,
            "article": a.number,
            "title": a.title,
            "text": a.full_text,
            "score": a.score,
        }
        for a in articles
    ]
    return json.dumps({"articles": payload}, ensure_ascii=False)


async def handle_rag_search(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    """Единственный боевой путь rag_search: вызывается из реестра тулзов.

    Область поиска берётся ТОЛЬКО из `ctx.acts` (выбор пользователя в UI):
    схема тулзы не объявляет `acts`, и даже если модель их выдумает,
    расширить область она не может.
    """
    raw = arguments.get("query")
    query = (raw.strip() if isinstance(raw, str) else "")[:SEARCH_QUERY_MAX_CHARS]
    if not query:
        return ToolOutcome(json.dumps({"error": "empty query"}, ensure_ascii=False))
    rs = ctx.tools.rag_search
    min_score = rs.min_score if rs.min_score > 0.0 else None
    try:
        articles = await ctx.rag_client.search(
            query, acts=ctx.acts, limit=rs.limit, min_score=min_score
        )
    except RagClientError:
        return ToolOutcome(
            json.dumps({"error": "search unavailable"}, ensure_ascii=False), unavailable=True
        )
    return ToolOutcome(_format_articles(articles), articles=articles)
