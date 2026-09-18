import pytest

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.chat.tools.list_acts import handle
from neurolegal.agent.tools.rag_client import RagClientError
from neurolegal.contracts import ActSummary, ToolsSettings


class _FakeRagOk:
    async def list_acts(self) -> list[ActSummary]:
        return [ActSummary(short_name="ГК РФ", full_name="Гражданский кодекс РФ", kind="codex")]


class _FakeRagFail:
    async def list_acts(self) -> list[ActSummary]:
        raise RagClientError("catalog unavailable")


def _ctx(rag: object) -> ToolContext:
    return ToolContext(
        rag_client=rag,  # type: ignore[arg-type]
        acts=None,
        tools=ToolsSettings(),
    )


@pytest.mark.asyncio
async def test_lists_acts() -> None:
    out: ToolOutcome = await handle({}, _ctx(_FakeRagOk()))
    assert "ГК РФ" in out.tool_result
    assert out.articles == []
    assert out.web_sources == []


@pytest.mark.asyncio
async def test_unavailable() -> None:
    out: ToolOutcome = await handle({}, _ctx(_FakeRagFail()))
    assert out.unavailable is True
