from typing import Annotated

from fastapi import APIRouter, Depends

from neurolegal.contracts import EmbedRequest, EmbedResponse
from neurolegal.rag.api.deps import get_embedder
from neurolegal.rag.embedding import Embedder

router = APIRouter()


@router.post("/embed", response_model=EmbedResponse)
async def embed(
    req: EmbedRequest,
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> EmbedResponse:
    vectors = await embedder.embed(req.texts)
    return EmbedResponse(vectors=vectors)
