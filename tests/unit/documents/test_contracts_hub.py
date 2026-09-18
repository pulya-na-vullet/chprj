from datetime import UTC, datetime

from neurolegal.contracts import (
    HubDocumentContent,
    HubDocumentInfo,
    HubSection,
)


def test_info_and_content_roundtrip():
    info = HubDocumentInfo(
        id="d1",
        owner_id="default",
        filename="c.docx",
        content_type="application/octet-stream",
        size=10,
        status="ready",
        parser="docx",
        page_count=None,
        error=None,
        created_at=datetime.now(UTC),
    )
    assert info.model_dump()["status"] == "ready"
    # T-0017: summary опционален (None для ещё-не-посчитанных и legacy-доков)
    assert info.summary is None
    with_summary = info.model_copy(update={"summary": "Поставка; оплата 10 дней"})
    assert with_summary.model_dump()["summary"] == "Поставка; оплата 10 дней"
    content = HubDocumentContent(
        id="d1",
        status="ready",
        full_text="hi",
        sections=[HubSection(number="1", title="T", text="body", level=1, start=0, end=4)],
    )
    assert content.sections[0].number == "1"


def test_upload_response_wraps_info():
    from neurolegal.contracts import HubDocumentInfo, UploadResponse

    info = HubDocumentInfo(
        id="d1",
        owner_id="default",
        filename="c.docx",
        content_type="application/octet-stream",
        size=10,
        status="processing",
        parser="docx",
        page_count=None,
        error=None,
        created_at=datetime.now(UTC),
    )
    resp = UploadResponse(document=info, session_id="conv-1")
    assert resp.session_id == "conv-1"
    assert resp.document.status == "processing"
