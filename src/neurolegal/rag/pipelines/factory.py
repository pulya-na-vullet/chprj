from typing import Literal

from neurolegal.core.config import settings
from neurolegal.rag.acquisition import Acquirer
from neurolegal.rag.acquisition.corpus_store import CorpusStore
from neurolegal.rag.acquisition.docx import DocxAcquirer
from neurolegal.rag.acquisition.local_docx import LocalDocxAcquirer
from neurolegal.rag.acquisition.manifest import Manifest
from neurolegal.rag.acquisition.pravo_gov import PravoGovAcquirer
from neurolegal.rag.acquisition.s3_docx import S3DocxAcquirer
from neurolegal.rag.chunking import ChunkStrategy
from neurolegal.rag.embedding import Embedder
from neurolegal.rag.parsing import Parser
from neurolegal.rag.parsing.docx import DocxParser
from neurolegal.rag.parsing.pravo_gov_html import PravoGovHTMLParser
from neurolegal.rag.pipelines.ingest import IngestPipeline, SessionFactory

SourceName = Literal["docx", "pravo"]


def build_pipeline(
    source: SourceName,
    *,
    manifest: Manifest,
    embedder: Embedder,
    session_factory: SessionFactory,
    chunk_strategy: ChunkStrategy = ChunkStrategy.PER_POINT,
    embed_batch_size: int | None = None,
    corpus_store: CorpusStore | None = None,
) -> IngestPipeline:
    acquirer: Acquirer
    parser: Parser
    match source:
        case "docx":
            acquirer = DocxAcquirer(
                manifest,
                local=LocalDocxAcquirer(manifest),
                s3=S3DocxAcquirer(manifest, corpus_store) if corpus_store else None,
            )
            parser = DocxParser(manifest)
        case "pravo":
            acquirer = PravoGovAcquirer(manifest)
            parser = PravoGovHTMLParser(manifest)
    return IngestPipeline(
        acquirer=acquirer,
        parser=parser,
        embedder=embedder,
        session_factory=session_factory,
        embed_batch_size=(
            embed_batch_size if embed_batch_size is not None else settings.embed_batch_size
        ),
        chunk_strategy=chunk_strategy,
    )
