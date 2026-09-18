import os
from pathlib import Path

import pytest

from neurolegal.rag.acquisition.corpus_store import build_corpus_store
from neurolegal.rag.acquisition.manifest import load_manifest
from neurolegal.rag.embedding import make_embedder
from neurolegal.rag.pipelines.factory import build_pipeline
from neurolegal.rag.store.db import get_sessionmaker

CORPUS = Path(__file__).parent.parent.parent / "corpus"

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(
    not (CORPUS / "manifest.yaml").exists()
    or os.environ.get("NEUROLEGAL_E2E") != "1"
    or not os.environ.get("DATABASE_URL")
    or not os.environ.get("OPENROUTER_API_KEY")
    or not os.environ.get("NEUROLEGAL_S3_ACCESS_KEY")
    or not os.environ.get("NEUROLEGAL_S3_SECRET_KEY"),
    reason=(
        "requires manifest, NEUROLEGAL_E2E=1, DATABASE_URL, OPENROUTER_API_KEY "
        "and S3 credentials (the corpus lives in the bucket)"
    ),
)
async def test_ingest_gk1_smoke() -> None:
    manifest = load_manifest()
    pipeline = build_pipeline(
        "docx",
        manifest=manifest,
        embedder=make_embedder(),
        session_factory=get_sessionmaker(),
        corpus_store=build_corpus_store(),
    )
    result = await pipeline.run("ГК-1")
    assert result.articles_count > 430
    assert result.chunks_count > 1500
