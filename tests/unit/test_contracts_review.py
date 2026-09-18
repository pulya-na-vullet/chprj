import pytest
from pydantic import ValidationError

from neurolegal.agent.chat.events import ReviewProgressEvent, ReviewReportEvent
from neurolegal.contracts import (
    AskEventData,
    ChatRequest,
    MessageAsk,
    MessageOut,
    PlaybookInfo,
    ReviewCommand,
    ReviewListItem,
    ReviewReportData,
    ReviewsResponse,
)


def test_chat_request_accepts_command() -> None:
    req = ChatRequest.model_validate(
        {
            "message": "Проверь договор",
            "command": {"type": "risk_review", "document_id": "d1", "playbook_id": "services_ru"},
        }
    )
    assert req.command is not None and req.command.playbook_id == "services_ru"


def test_review_command_role_optional() -> None:
    without_role = ReviewCommand.model_validate(
        {"type": "risk_review", "document_id": "d1", "playbook_id": "services_ru"}
    )
    assert without_role.role is None

    with_role = ReviewCommand.model_validate(
        {
            "type": "risk_review",
            "document_id": "d1",
            "playbook_id": "services_ru",
            "role": "Заказчик",
        }
    )
    assert with_role.role == "Заказчик"


def test_review_command_role_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewCommand.model_validate(
            {
                "type": "risk_review",
                "document_id": "d1",
                "playbook_id": "services_ru",
                "role": "x" * 101,
            }
        )


def test_review_report_data_role_optional() -> None:
    # Old reports persisted before T-0046 have no `role` field at all — must
    # still validate (backward compat for rows already in the DB).
    legacy = ReviewReportData.model_validate(
        {
            "playbook_id": "p",
            "playbook_name": "n",
            "document_id": "d",
            "risks": [],
            "coverage": [],
            "disclaimer": "…",
        }
    )
    assert legacy.role is None

    with_role = ReviewReportData.model_validate(
        {
            "playbook_id": "p",
            "playbook_name": "n",
            "document_id": "d",
            "risks": [],
            "coverage": [],
            "disclaimer": "…",
            "role": "Исполнитель",
        }
    )
    assert with_role.role == "Исполнитель"


def test_review_report_data_summary_optional() -> None:
    # T-0047: old reports persisted before the summary field have no `summary`
    # key — must still validate, reading as None.
    legacy = ReviewReportData.model_validate(
        {
            "playbook_id": "p",
            "playbook_name": "n",
            "document_id": "d",
            "risks": [],
            "coverage": [],
            "disclaimer": "…",
        }
    )
    assert legacy.summary is None

    with_summary = ReviewReportData.model_validate(
        {
            "playbook_id": "p",
            "playbook_name": "n",
            "document_id": "d",
            "risks": [],
            "coverage": [],
            "disclaimer": "…",
            "summary": "Договор в целом сбалансирован.",
        }
    )
    assert with_summary.summary == "Договор в целом сбалансирован."


def test_review_list_item_done_and_failed() -> None:
    # T-0048: элемент свода GET /reviews — done несёт счётчики уровней,
    # failed несёт текст ошибки; документные поля опциональны (документ мог
    # быть удалён из библиотеки).
    done = ReviewListItem.model_validate(
        {
            "message_id": "m1",
            "conversation_id": "c1",
            "playbook_id": "supply_ru",
            "playbook_name": "Договор поставки",
            "document_id": "d1",
            "document_filename": "договор.pdf",
            "document_parser": "pdf",
            "role": "Покупатель",
            "status": "done",
            "high": 2,
            "medium": 1,
            "low": 0,
            "rules_total": 12,
            "created_at": "2026-07-18T12:00:00+00:00",
        }
    )
    assert done.status == "done" and done.high == 2 and done.error is None

    failed = ReviewListItem.model_validate(
        {
            "message_id": "m2",
            "conversation_id": "c2",
            "playbook_id": "services_ru",
            "playbook_name": "Возмездное оказание услуг",
            "document_id": "d2",
            "status": "failed",
            "error": "Сервис документов недоступен",
            "created_at": "2026-07-18T12:00:00+00:00",
        }
    )
    assert failed.status == "failed"
    assert failed.document_filename is None and failed.role is None
    assert failed.high == 0 and failed.rules_total == 0

    resp = ReviewsResponse(items=[done, failed], total=2)
    assert resp.total == 2


def test_playbook_info_roles_optional_backcompat() -> None:
    # T-0048: `roles` появились для формы «Новая проверка»; старые клиенты
    # без поля остаются валидны.
    legacy = PlaybookInfo.model_validate({"id": "p", "name": "П", "rules_count": 3})
    assert legacy.roles == []

    with_roles = PlaybookInfo.model_validate(
        {"id": "p", "name": "П", "rules_count": 3, "roles": ["Покупатель", "Поставщик"]}
    )
    assert with_roles.roles == ["Покупатель", "Поставщик"]


def test_message_ask_roundtrip_review_role() -> None:
    ask = MessageAsk.model_validate(
        {
            "kind": "review_role",
            "question": "На чьей вы стороне?",
            "options": ["Заказчик", "Исполнитель"],
            "document_id": "d1",
            "playbook_id": "services_ru",
        }
    )
    dumped = ask.model_dump()
    restored = MessageAsk.model_validate(dumped)
    assert restored == ask
    assert restored.kind == "review_role"
    assert restored.options == ["Заказчик", "Исполнитель"]
    assert restored.role is None and restored.error is None


def test_message_ask_roundtrip_review_failed() -> None:
    ask = MessageAsk.model_validate(
        {
            "kind": "review_failed",
            "document_id": "d1",
            "playbook_id": "services_ru",
            "role": "Заказчик",
            "error": "не удалось построить отчёт",
        }
    )
    dumped = ask.model_dump()
    restored = MessageAsk.model_validate(dumped)
    assert restored == ask
    assert restored.kind == "review_failed"
    assert restored.question is None
    assert restored.options == []
    assert restored.error == "не удалось построить отчёт"


def test_message_ask_options_default_not_shared() -> None:
    # Field(default_factory=list) — guards against a mutable-default footgun
    # (a bare `= []` class attribute would be shared across instances).
    a = MessageAsk.model_validate({"kind": "review_role"})
    b = MessageAsk.model_validate({"kind": "review_role"})
    a.options.append("x")
    assert b.options == []


def test_message_out_ask_field_defaults_none() -> None:
    msg = MessageOut.model_validate(
        {
            "id": "m1",
            "role": "assistant",
            "content": "…",
            "citations": None,
            "created_at": "2026-07-18T00:00:00Z",
        }
    )
    assert msg.ask is None

    with_ask = MessageOut.model_validate(
        {
            "id": "m2",
            "role": "assistant",
            "content": "…",
            "citations": None,
            "created_at": "2026-07-18T00:00:00Z",
            "ask": {"kind": "review_role", "question": "На чьей вы стороне?"},
        }
    )
    assert with_ask.ask is not None and with_ask.ask.kind == "review_role"


def test_ask_event_data_roundtrip() -> None:
    ev = AskEventData.model_validate(
        {"question": "На чьей вы стороне?", "options": ["Заказчик", "Исполнитель"]}
    )
    assert ev.allow_free_text is True
    dumped = ev.model_dump()
    restored = AskEventData.model_validate(dumped)
    assert restored == ev


def test_review_events_shape() -> None:
    ev = ReviewProgressEvent(rule_id="r1", title="Оплата", index=1, total=15, status="running")
    assert ev.event == "review_progress" and ev.data["total"] == 15
    report = ReviewReportData(
        playbook_id="p",
        playbook_name="n",
        document_id="d",
        risks=[],
        coverage=[],
        disclaimer="…",
    )
    rev = ReviewReportEvent(report=report)
    assert rev.event == "review_report" and rev.data["playbook_id"] == "p"
