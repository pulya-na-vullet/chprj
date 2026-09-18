"""Tool registry: maps enabled tool names to (ToolSpec, ToolHandler) pairs."""

from neurolegal.agent.chat.tools import (
    date_calculator,
    fetch_article,
    list_acts,
    rag_search,
    web_fetch,
    web_search,
)
from neurolegal.agent.chat.tools.base import ToolHandler
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.contracts import ToolsSettings

RegisteredTool = tuple[ToolSpec, ToolHandler]


def build_registry(tools: ToolsSettings) -> dict[str, RegisteredTool]:
    candidates: list[tuple[bool, ToolSpec, ToolHandler]] = [
        (tools.rag_search.enabled, rag_search.RAG_SEARCH_TOOL, rag_search.handle_rag_search),
        (tools.fetch_article.enabled, fetch_article.FETCH_ARTICLE_TOOL, fetch_article.handle),
        (tools.list_acts.enabled, list_acts.LIST_ACTS_TOOL, list_acts.handle),
        (tools.date_calculator.enabled, date_calculator.DATE_CALC_TOOL, date_calculator.handle),
        (tools.web_search.enabled, web_search.WEB_SEARCH_TOOL, web_search.handle),
        (tools.web_fetch.enabled, web_fetch.WEB_FETCH_TOOL, web_fetch.handle),
    ]
    return {spec.name: (spec, h) for enabled, spec, h in candidates if enabled}
