"""RAG CLI: ingest / reindex / search.

Invoked as ``neurolegal rag <subcommand>`` via the top-level dispatcher in
``neurolegal.cli.main``.
"""

import asyncio
import json
from typing import Annotated, Literal

import typer

from neurolegal.core.logging_setup import configure_logging
from neurolegal.rag.acquisition.corpus_store import build_corpus_store_or_none
from neurolegal.rag.acquisition.manifest import load_manifest
from neurolegal.rag.embedding import make_embedder
from neurolegal.rag.pipelines.factory import build_pipeline
from neurolegal.rag.retrieval import RetrievalService
from neurolegal.rag.store.db import get_sessionmaker
from neurolegal.rag.store.indexes import (
    create_search_indexes,
    drop_search_indexes,
    inspect_search_indexes,
)

app = typer.Typer(no_args_is_help=True, help="RAG commands (ingest / search).")

SourceName = Literal["docx", "pravo"]


@app.command()
def ingest(
    codes: Annotated[list[str], typer.Option("--code", help="Code id (repeatable)")],
    source: Annotated[SourceName, typer.Option("--source")] = "docx",
    bulk: Annotated[
        bool,
        typer.Option(
            "--bulk",
            help="Drop HNSW+GIN before, recreate after; required when the index is "
            "large (~30k+ vectors) or per-insert maintenance trips Neon's timeout.",
        ),
    ] = False,
) -> None:
    """Run the full ingestion pipeline for one or more acts."""
    configure_logging()

    async def run() -> None:
        manifest = load_manifest()
        session_factory = get_sessionmaker()
        # Без кредов используем только локальные docx_path — DocxAcquirer
        # объяснит это внятной ошибкой, если запись указывает на S3.
        pipeline = build_pipeline(
            source,
            manifest=manifest,
            embedder=make_embedder(),
            session_factory=session_factory,
            corpus_store=build_corpus_store_or_none(),
        )

        if bulk:
            async with session_factory() as session:
                await drop_search_indexes(session)

        try:
            for code in codes:
                result = await pipeline.run(code)
                typer.echo(
                    json.dumps(
                        {
                            "act_id": result.act_id,
                            "code": code,
                            "articles": result.articles_count,
                            "chunks": result.chunks_count,
                        },
                        ensure_ascii=False,
                    )
                )
        finally:
            if bulk:
                async with session_factory() as session:
                    await create_search_indexes(session)

    asyncio.run(run())


@app.command()
def reindex(
    code: Annotated[str, typer.Option("--code", help="Code id")],
    source: Annotated[SourceName, typer.Option("--source")] = "docx",
) -> None:
    """Re-run ingestion (uses raw cache for pravo; reads file for docx)."""
    configure_logging()

    async def run() -> None:
        manifest = load_manifest()
        pipeline = build_pipeline(
            source,
            manifest=manifest,
            embedder=make_embedder(),
            session_factory=get_sessionmaker(),
            corpus_store=build_corpus_store_or_none(),
        )
        await pipeline.run(code)

    asyncio.run(run())


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    acts: Annotated[list[str] | None, typer.Option("--act")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 8,
) -> None:
    """Run a search and print results as JSON."""
    configure_logging()

    async def run() -> None:
        svc = RetrievalService(make_embedder())
        async with get_sessionmaker()() as session:
            results = await svc.search(session, query, acts=acts, limit=limit)
        typer.echo(
            json.dumps(
                [r.model_dump(mode="json") for r in results],
                ensure_ascii=False,
                indent=2,
            )
        )

    asyncio.run(run())


indexes_app = typer.Typer(no_args_is_help=True, help="Search-index runbook commands.")
app.add_typer(indexes_app, name="indexes")


@indexes_app.command("status")
def indexes_status() -> None:
    """Print live HNSW/GIN index presence (queries pg_indexes)."""
    configure_logging()

    async def run() -> None:
        async with get_sessionmaker()() as session:
            present = await inspect_search_indexes(session)
        typer.echo(json.dumps(present, ensure_ascii=False))

    asyncio.run(run())


@indexes_app.command("drop")
def indexes_drop() -> None:
    """Drop HNSW + GIN search indexes (use before a bulk ingest)."""
    configure_logging()

    async def run() -> None:
        async with get_sessionmaker()() as session:
            await drop_search_indexes(session)

    asyncio.run(run())


@indexes_app.command("create")
def indexes_create() -> None:
    """(Re)create HNSW + GIN search indexes."""
    configure_logging()

    async def run() -> None:
        async with get_sessionmaker()() as session:
            await create_search_indexes(session)

    asyncio.run(run())


if __name__ == "__main__":
    app()
