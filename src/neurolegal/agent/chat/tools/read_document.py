"""Tool: read_document — read a document uploaded to this conversation.

read_document validates the id against ctx.document_ids (the hub's ready
documents for this conversation) and fetches section content from the hub on
demand.
"""

import json

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import ToolSpec
from neurolegal.agent.tools.documents_client import DocumentsClientError

SECTION_TEXT_LIMIT = 8000
OUTLINE_TEXT_LIMIT = 4000

READ_DOCUMENT_TOOL = ToolSpec(
    name="read_document",
    description=(
        "Прочитать документ, загруженный в этой беседе. Без section_number "
        "возвращает оглавление и начало текста документа; с section_number — "
        "текст конкретного раздела/пункта."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "ID документа."},
            "section_number": {
                "type": "string",
                "description": "Номер раздела/пункта документа (необязательно).",
            },
        },
        "required": ["document_id"],
    },
)


async def handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    document_id = str(arguments.get("document_id", "")).strip()
    if document_id not in ctx.document_ids or ctx.documents_client is None:
        return ToolOutcome(json.dumps({"error": "document not found"}, ensure_ascii=False))
    try:
        content = await ctx.documents_client.get_content(document_id, ctx.user_id)
    except DocumentsClientError:
        return ToolOutcome(json.dumps({"error": "document unavailable"}, ensure_ascii=False))
    sections = [s.model_dump() for s in content.sections]

    section_number = arguments.get("section_number")
    if section_number is not None:
        number = str(section_number).strip()
        for section in sections:
            if str(section.get("number")) == number:
                payload = {**section, "text": str(section.get("text", ""))[:SECTION_TEXT_LIMIT]}
                return ToolOutcome(json.dumps(payload, ensure_ascii=False))
        return ToolOutcome(json.dumps({"error": "section not found"}, ensure_ascii=False))

    outline = [
        {"number": s.get("number"), "title": s.get("title"), "level": s.get("level")}
        for s in sections
    ]
    text = "".join(str(s.get("text", "")) for s in sections)[:OUTLINE_TEXT_LIMIT]
    return ToolOutcome(json.dumps({"outline": outline, "text": text}, ensure_ascii=False))
