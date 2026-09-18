"""Unit tests for the read_document tool against a fake DocumentsClient."""

import json

import pytest

from neurolegal.agent.chat.tools.base import ToolContext
from neurolegal.agent.chat.tools.read_document import handle
from neurolegal.agent.tools.documents_client import DocumentsClientError
from neurolegal.contracts import HubDocumentContent, HubSection, ToolsSettings

SECTIONS = [
    HubSection(number="1", title="Предмет", text="1. Предмет\nТекст.", level=1, start=0, end=10),
    HubSection(number="2", title="Оплата", text="2. Оплата\n10 дней.", level=1, start=10, end=20),
]


class _FakeClient:
    def __init__(self, *, boom: bool = False) -> None:
        self._boom = boom

    async def get_content(self, document_id: str, user_id: str) -> HubDocumentContent:
        if self._boom:
            raise DocumentsClientError("down")
        return HubDocumentContent(id=document_id, status="ready", full_text="x", sections=SECTIONS)


def _ctx(client, ids=frozenset({"d1"})) -> ToolContext:
    return ToolContext(
        rag_client=None,  # type: ignore[arg-type]
        acts=None,
        tools=ToolsSettings(),
        document_ids=ids,
        documents_client=client,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_outline_when_no_section_number():
    out = await handle({"document_id": "d1"}, _ctx(_FakeClient()))
    payload = json.loads(out.tool_result)
    assert [s["number"] for s in payload["outline"]] == ["1", "2"]
    assert "Предмет" in payload["text"]


@pytest.mark.asyncio
async def test_specific_section():
    out = await handle({"document_id": "d1", "section_number": "2"}, _ctx(_FakeClient()))
    payload = json.loads(out.tool_result)
    assert payload["number"] == "2" and "Оплата" in payload["text"]


@pytest.mark.asyncio
async def test_unknown_id_is_not_found():
    out = await handle({"document_id": "nope"}, _ctx(_FakeClient()))
    assert json.loads(out.tool_result) == {"error": "document not found"}


@pytest.mark.asyncio
async def test_client_error_degrades():
    out = await handle({"document_id": "d1"}, _ctx(_FakeClient(boom=True)))
    assert json.loads(out.tool_result) == {"error": "document unavailable"}
