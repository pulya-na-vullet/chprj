"""GET /reviews — свод risk-review прогонов для раздела «Проверки» (T-0048).

Свод собирается из двух видов сообщений (ConversationStore.list_review_runs):
готовый отчёт в `messages.review` (status="done") и сбойный прогон в
`messages.ask` (kind="review_failed", status="failed"). Имя/тип документа
подтягиваются одним вызовом сервиса документов; недоступность этого
сервиса деградирует до пустых имён вместо 500 — список прогонов живёт и так.
"""

import logging
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from neurolegal.agent.api.deps import get_documents_client, get_playbooks, get_store
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.review.export import build_docx_report
from neurolegal.agent.review.playbook import Playbook
from neurolegal.agent.store.conversation_store import ConversationStore, ReviewRunRow
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.documents_client import DocumentsClient, DocumentsClientError
from neurolegal.contracts import HubDocumentInfo, ReviewListItem, ReviewReportData, ReviewsResponse

logger = logging.getLogger(__name__)

router = APIRouter()

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _item(
    run: ReviewRunRow,
    docs_by_id: dict[str, HubDocumentInfo],
    playbooks: dict[str, Playbook],
) -> ReviewListItem:
    if run.review is not None:
        report = run.review
        risks_raw = report.get("risks")
        risks = risks_raw if isinstance(risks_raw, list) else []
        levels = [r.get("level") for r in risks if isinstance(r, dict)]
        playbook_id = str(report.get("playbook_id") or "")
        document_id = str(report.get("document_id") or "")
        doc = docs_by_id.get(document_id)
        role = report.get("role")
        return ReviewListItem(
            message_id=run.message_id,
            conversation_id=run.conversation_id,
            playbook_id=playbook_id,
            playbook_name=str(report.get("playbook_name") or playbook_id),
            document_id=document_id,
            document_filename=doc.filename if doc else None,
            document_parser=doc.parser if doc else None,
            role=str(role) if role else None,
            status="done",
            high=levels.count("high"),
            medium=levels.count("medium"),
            low=levels.count("low"),
            rules_total=len(coverage)
            if isinstance(coverage := report.get("coverage"), list)
            else 0,
            created_at=run.created_at.isoformat(),
        )
    ask = run.ask or {}
    playbook_id = str(ask.get("playbook_id") or "")
    document_id = str(ask.get("document_id") or "")
    doc = docs_by_id.get(document_id)
    playbook = playbooks.get(playbook_id)
    role = ask.get("role")
    error = ask.get("error")
    return ReviewListItem(
        message_id=run.message_id,
        conversation_id=run.conversation_id,
        playbook_id=playbook_id,
        playbook_name=playbook.name if playbook else playbook_id,
        document_id=document_id,
        document_filename=doc.filename if doc else None,
        document_parser=doc.parser if doc else None,
        role=str(role) if role else None,
        status="failed",
        error=str(error) if error else None,
        created_at=run.created_at.isoformat(),
    )


@router.get("/reviews", response_model=ReviewsResponse)
async def list_reviews(
    store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
    documents: Annotated[DocumentsClient, Depends(get_documents_client)],
    playbooks: Annotated[dict[str, Playbook], Depends(get_playbooks)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewsResponse:
    runs = await store.list_review_runs(user.id)
    try:
        owner_docs = await documents.list_for_owner(user.id)
    except DocumentsClientError:
        logger.warning("reviews_documents_lookup_failed", extra={"user_id": user.id})
        owner_docs = []
    docs_by_id = {d.id: d for d in owner_docs}
    page = runs[offset : offset + limit]
    return ReviewsResponse(
        items=[_item(run, docs_by_id, playbooks) for run in page],
        total=len(runs),
    )


@router.get("/reviews/{message_id}/export")
async def export_review(
    message_id: str,
    store: Annotated[ConversationStore, Depends(get_store)],
    user: Annotated[UserRow, Depends(get_current_user)],
    documents: Annotated[DocumentsClient, Depends(get_documents_client)],
    format: Annotated[Literal["docx"], Query()] = "docx",
) -> Response:
    """Скачивание отчёта файлом (T-0049). Пока единственный формат — DOCX;
    PDF отдаёт фронт печатью панели (решение плана T-0049)."""
    run = await store.get_review_report(message_id, user.id)
    if run is None or run.review is None:
        raise HTTPException(status_code=404, detail="review not found")
    report = ReviewReportData.model_validate(run.review)

    document_filename: str | None = None
    if report.document_id:
        try:
            info = await documents.get_info(report.document_id, user.id)
            document_filename = info.filename
        except DocumentsClientError:
            logger.warning(
                "review_export_document_lookup_failed",
                extra={"message_id": message_id},
            )

    data = build_docx_report(report, document_filename=document_filename, created_at=run.created_at)
    pretty = f"Проверка — {report.playbook_name}.docx"
    # safe="" — RFC 5987 ext-value не допускает неэкранированный "/"
    disposition = f"attachment; filename=\"review.docx\"; filename*=UTF-8''{quote(pretty, safe='')}"
    return Response(
        content=data,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": disposition},
    )
