"""Admin routes: ingest jobs (start / poll / cancel) and index status."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts.admin import (
    IndexesStatusResponse,
    IngestAccepted,
    IngestRequest,
    JobOut,
    JobsResponse,
    OkResponse,
)
from neurolegal.rag.acquisition.manifest import load_manifest
from neurolegal.rag.api.deps import db_session, get_job_manager, get_manifest_path
from neurolegal.rag.jobs import JobBusyError, JobManager, JobRecord
from neurolegal.rag.store.indexes import inspect_search_indexes

router = APIRouter(prefix="/admin")

_DbSession = Annotated[AsyncSession, Depends(db_session)]
_ManifestPath = Annotated[Path, Depends(get_manifest_path)]
_Jobs = Annotated[JobManager, Depends(get_job_manager)]


def _to_out(job: JobRecord) -> JobOut:
    return JobOut.model_validate(job.as_dict())


@router.post("/ingest", response_model=IngestAccepted, status_code=202)
async def start_ingest(
    req: IngestRequest, manifest_path: _ManifestPath, jobs: _Jobs
) -> IngestAccepted:
    manifest = load_manifest(manifest_path)
    entry = manifest.entries.get(req.code_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown code_id {req.code_id!r}")
    if entry.docx_path is not None and not Path(entry.docx_path).is_file():
        raise HTTPException(status_code=422, detail=f"docx file is missing: {entry.docx_path}")
    try:
        job = jobs.start(req.code_id)
    except JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestAccepted(job_id=job.id)


@router.get("/jobs", response_model=JobsResponse)
async def jobs_list(jobs: _Jobs) -> JobsResponse:
    return JobsResponse(jobs=[_to_out(j) for j in jobs.list()])


@router.get("/jobs/{job_id}", response_model=JobOut)
async def job_get(job_id: str, jobs: _Jobs) -> JobOut:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _to_out(job)


@router.post("/jobs/{job_id}/cancel", response_model=OkResponse)
async def job_cancel(job_id: str, jobs: _Jobs) -> OkResponse:
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=404, detail="no running job with this id")
    return OkResponse()


@router.get("/indexes", response_model=IndexesStatusResponse)
async def indexes_status(session: _DbSession) -> IndexesStatusResponse:
    present = await inspect_search_indexes(session)
    return IndexesStatusResponse(
        hnsw=present["chunks_embedding_hnsw"], gin=present["chunks_search_vector_gin"]
    )
