"""Lightweight assertion that the contracts package exists and re-exports the
DTOs every other layer needs. The point isn't behaviour — it's that the import
path is stable, so route modules and the client don't reach into private
packages."""

import importlib


def test_contracts_package_importable() -> None:
    mod = importlib.import_module("neurolegal.contracts")
    for name in (
        "SearchedArticle",
        "SearchedChunk",
        "SearchResponse",
        "RetrieveRequest",
        "EmbedRequest",
        "EmbedResponse",
        "ActSummary",
        "ActsResponse",
        "ChatRequest",
        "Citation",
        "FoundArticle",
        "ConversationOut",
        "ConversationsResponse",
        "MessageOut",
        "MessagesResponse",
        "SessionEventData",
        "ReasoningEventData",
        "ToolCallEventData",
        "ToolResultEventData",
        "DeltaEventData",
        "ResetDeltaEventData",
        "CitationsEventData",
        "DoneEventData",
        "ErrorEventData",
        "AdminDocument",
        "AdminDocumentsResponse",
        "ManifestUpdateRequest",
        "DeleteDocumentRequest",
        "UploadDocumentResponse",
        "IngestRequest",
        "IngestAccepted",
        "JobOut",
        "JobsResponse",
        "AdminArticleListItem",
        "AdminArticlesResponse",
        "AdminChunkOut",
        "AdminArticleDetail",
        "IndexesStatusResponse",
        "OkResponse",
    ):
        assert hasattr(mod, name), f"contracts must re-export {name}"
