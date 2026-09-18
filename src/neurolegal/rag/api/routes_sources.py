"""Always-on, client-safe read-only catalog of legal sources.

Powers the «Источники права» screen. Unlike /admin/* this is never gated on
admin_enabled and never exposes operator internals (paths, mtime, jobs, chunk
counts). Reuses the admin store queries.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import (
    SourceArticleDetail,
    SourceArticleListItem,
    SourceArticlesResponse,
    SourcesResponse,
)
from neurolegal.rag.acquisition.manifest import load_manifest
from neurolegal.rag.api.deps import db_session, get_manifest_path
from neurolegal.rag.sources_view import build_sources
from neurolegal.rag.store.admin import act_stats, article_detail, list_articles

router = APIRouter()

_DbSession = Annotated[AsyncSession, Depends(db_session)]
_ManifestPath = Annotated[Path, Depends(get_manifest_path)]


@router.get("/sources", response_model=SourcesResponse)
async def sources(session: _DbSession, manifest_path: _ManifestPath) -> SourcesResponse:
    manifest = load_manifest(manifest_path)
    stats = await act_stats(session)
    return SourcesResponse(sources=build_sources(manifest, stats))


@router.get("/sources/{source_doc_id}/articles", response_model=SourceArticlesResponse)
async def source_articles(
    source_doc_id: str, session: _DbSession, manifest_path: _ManifestPath
) -> SourceArticlesResponse:
    manifest = load_manifest(manifest_path)
    short_name = next(
        (e.short_name for e in manifest.entries.values() if e.source_doc_id == source_doc_id),
        source_doc_id,
    )
    entries = await list_articles(session, source_doc_id)
    return SourceArticlesResponse(
        source_doc_id=source_doc_id,
        short_name=short_name,
        articles=[
            SourceArticleListItem(article_id=e.article_id, number=e.number, title=e.title)
            for e in entries
        ],
    )


@router.get("/sources/articles/{article_id}", response_model=SourceArticleDetail)
async def article(article_id: str, session: _DbSession) -> SourceArticleDetail:
    detail = await article_detail(session, article_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="article not found")
    return SourceArticleDetail(
        article_id=detail.article_id,
        act_short_name=detail.act_short_name,
        number=detail.number,
        title=detail.title,
        full_text=detail.full_text,
    )
