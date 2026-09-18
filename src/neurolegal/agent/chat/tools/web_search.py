"""Tool: web_search — search the web for context via Tavily."""

import json

import httpx

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.contracts import WebSource
from neurolegal.core.http import make_http_retry

WEB_SEARCH_TOOL = ToolSpec(
    name="web_search",
    description=(
        "Поиск в интернете для контекста (новости, актуальность, неправовые факты). "
        "НЕ является основанием для правовой нормы — нормы только из rag_search/fetch_article."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    },
)

_UNAVAILABLE = json.dumps({"error": "web search unavailable"}, ensure_ascii=False)


async def handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return ToolOutcome(json.dumps({"error": "empty query"}, ensure_ascii=False))
    if not ctx.tavily_api_key:
        return ToolOutcome(_UNAVAILABLE)

    cap = ctx.tools.web_search.max_results
    requested = arguments.get("max_results")
    n = min(int(requested), cap) if isinstance(requested, int) else cap

    try:
        async for attempt in make_http_retry():
            with attempt:
                async with httpx.AsyncClient(timeout=20.0) as c:
                    r = await c.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": ctx.tavily_api_key,
                            "query": query,
                            "max_results": n,
                        },
                    )
                    r.raise_for_status()
                    data = r.json()
    except (httpx.HTTPError, ValueError):
        return ToolOutcome(_UNAVAILABLE)

    results = data.get("results", []) if isinstance(data, dict) else []
    sources = [
        WebSource(
            url=str(item.get("url", "")),
            title=str(item.get("title", "")),
            snippet=item.get("content"),
        )
        for item in results
    ]
    payload = [{"url": s.url, "title": s.title, "snippet": s.snippet} for s in sources]
    return ToolOutcome(
        json.dumps({"results": payload}, ensure_ascii=False),
        web_sources=sources,
    )
