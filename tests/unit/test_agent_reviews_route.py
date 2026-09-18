"""GET /reviews (T-0048): свод risk-review прогонов для раздела «Проверки».

Паттерн test_agent_conversations_route.py: sqlite-стор + dependency_overrides
(get_store / get_current_user / get_documents_client / get_playbooks).
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_documents_client, get_playbooks, get_store
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.review.playbook import Playbook, PlaybookRule
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base, UserRow
from neurolegal.agent.tools.documents_client import DocumentsClientError
from neurolegal.contracts import HubDocumentInfo

USER_ID = "u1"


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield ConversationStore(session)
    await engine.dispose()


def _user() -> UserRow:
    return UserRow(
        id=USER_ID,
        email="u1@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def _doc(document_id: str, filename: str, parser: str = "docx") -> HubDocumentInfo:
    return HubDocumentInfo(
        id=document_id,
        owner_id=USER_ID,
        filename=filename,
        content_type="application/octet-stream",
        size=100,
        status="ready",
        parser=parser,
        created_at=datetime.now(UTC),
    )


class _FakeDocs:
    def __init__(self, docs: list[HubDocumentInfo]) -> None:
        self._docs = docs

    async def list_for_owner(self, owner_id: str) -> list[HubDocumentInfo]:
        return [d for d in self._docs if d.owner_id == owner_id]

    async def get_info(self, document_id: str, user_id: str) -> HubDocumentInfo:
        for d in self._docs:
            if d.id == document_id:
                return d
        raise DocumentsClientError("not found")


class _DownDocs:
    async def list_for_owner(self, owner_id: str) -> list[HubDocumentInfo]:
        raise DocumentsClientError("down")

    async def get_info(self, document_id: str, user_id: str) -> HubDocumentInfo:
        raise DocumentsClientError("hub down")


def _playbooks() -> dict[str, Playbook]:
    return {
        "supply_ru": Playbook(
            id="supply_ru",
            name="Договор поставки",
            rules=[PlaybookRule(id="r1", title="Правило", question="?")],
        )
    }


def _client(
    store: ConversationStore,
    docs: object | None = None,
) -> TestClient:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_documents_client] = lambda: (
        docs if docs is not None else _FakeDocs([])
    )
    app.dependency_overrides[get_playbooks] = _playbooks
    return TestClient(app)


_REPORT = {
    "playbook_id": "supply_ru",
    "playbook_name": "Договор поставки",
    "document_id": "d1",
    "risks": [
        {
            "rule_id": "r1",
            "title": "Оплата",
            "level": "high",
            "verdict": "confirmed",
            "contract_quote": "",
            "explanation": "",
            "recommendation": "",
        },
        {
            "rule_id": "r2",
            "title": "Сроки",
            "level": "medium",
            "verdict": "confirmed",
            "contract_quote": "",
            "explanation": "",
            "recommendation": "",
        },
    ],
    "coverage": [
        {"rule_id": "r1", "title": "Оплата", "status": "risk"},
        {"rule_id": "r2", "title": "Сроки", "status": "risk"},
        {"rule_id": "r3", "title": "Прочее", "status": "ok"},
    ],
    "disclaimer": "…",
    "role": "Покупатель",
    "summary": None,
}


async def _seed_done(store: ConversationStore) -> tuple[str, str]:
    conv = await store.create_conversation(USER_ID)
    await store.append_message(conv, USER_ID, "user", "проверь")
    msg = await store.append_message(conv, USER_ID, "assistant", "отчёт", review=_REPORT)
    await store.commit()
    return conv, msg


async def _seed_failed(store: ConversationStore) -> tuple[str, str]:
    conv = await store.create_conversation(USER_ID)
    msg = await store.append_message(
        conv,
        USER_ID,
        "assistant",
        "не удалось",
        ask={
            "kind": "review_failed",
            "document_id": "d2",
            "playbook_id": "supply_ru",
            "role": "Поставщик",
            "error": "Сервис документов недоступен",
        },
    )
    await store.commit()
    return conv, msg


@pytest.fixture(autouse=True)
def _cleanup() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


async def test_reviews_lists_done_run_with_counts_and_document(store: ConversationStore) -> None:
    conv, msg = await _seed_done(store)
    client = _client(store, docs=_FakeDocs([_doc("d1", "договор.docx")]))

    resp = client.get("/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["message_id"] == msg and item["conversation_id"] == conv
    assert item["status"] == "done"
    assert item["playbook_name"] == "Договор поставки"
    assert item["role"] == "Покупатель"
    assert (item["high"], item["medium"], item["low"]) == (1, 1, 0)
    assert item["rules_total"] == 3
    assert item["document_filename"] == "договор.docx"
    assert item["document_parser"] == "docx"


async def test_reviews_lists_failed_run_with_playbook_name_from_catalog(
    store: ConversationStore,
) -> None:
    await _seed_failed(store)
    client = _client(store)

    item = client.get("/reviews").json()["items"][0]
    assert item["status"] == "failed"
    assert item["playbook_name"] == "Договор поставки"  # имя из каталога по id
    assert item["role"] == "Поставщик"
    assert item["error"] == "Сервис документов недоступен"
    assert item["document_filename"] is None


async def test_reviews_survives_documents_hub_outage(store: ConversationStore) -> None:
    await _seed_done(store)
    client = _client(store, docs=_DownDocs())

    resp = client.get("/reviews")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["document_filename"] is None and item["document_parser"] is None


async def test_reviews_limit_offset(store: ConversationStore) -> None:
    await _seed_done(store)
    await _seed_failed(store)
    client = _client(store)

    page = client.get("/reviews", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["status"] == "done"  # новые первыми: failed → done


async def test_reviews_tolerates_malformed_report_json(store: ConversationStore) -> None:
    """Записи старых версий могут нести неполный/битый review-JSON — свод
    не должен падать: мусор в risks/coverage игнорируется, роль-не-строка
    приводится, имя плейбука падает обратно в id."""
    conv = await store.create_conversation(USER_ID)
    msg = await store.append_message(
        conv,
        USER_ID,
        "assistant",
        "отчёт",
        review={
            "playbook_id": "supply_ru",
            # playbook_name отсутствует; risks — не список; coverage — мусор
            "document_id": "d1",
            "risks": "мусор",
            "coverage": {"тоже": "мусор"},
            "role": 42,
        },
    )
    await store.commit()
    client = _client(store)

    resp = client.get("/reviews")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["message_id"] == msg
    assert item["playbook_name"] == "supply_ru"  # fallback на id
    assert (item["high"], item["medium"], item["low"]) == (0, 0, 0)
    assert item["rules_total"] == 0
    assert item["role"] == "42"


async def test_reviews_requires_auth(store: ConversationStore) -> None:
    _client(store)
    app.dependency_overrides.pop(get_current_user)
    client = TestClient(app)
    assert client.get("/reviews").status_code == 401


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def test_export_docx_returns_attachment(store: ConversationStore) -> None:
    _, msg = await _seed_done(store)
    client = _client(store, docs=_FakeDocs([_doc("d1", "dogovor.pdf")]))

    resp = client.get(f"/reviews/{msg}/export?format=docx")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(DOCX_MIME)
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="review.docx"')
    assert "filename*=UTF-8''" in disposition
    # .docx — это zip: сигнатура PK
    assert resp.content[:2] == b"PK"


async def test_export_survives_documents_hub_outage(store: ConversationStore) -> None:
    _, msg = await _seed_done(store)
    client = _client(store, docs=_DownDocs())
    resp = client.get(f"/reviews/{msg}/export?format=docx")
    assert resp.status_code == 200


async def test_export_404_for_missing_and_failed_run(store: ConversationStore) -> None:
    _, failed_msg = await _seed_failed(store)
    client = _client(store)
    assert client.get("/reviews/nope/export?format=docx").status_code == 404
    assert client.get(f"/reviews/{failed_msg}/export?format=docx").status_code == 404


async def test_export_422_for_unknown_format(store: ConversationStore) -> None:
    _, msg = await _seed_done(store)
    client = _client(store)
    assert client.get(f"/reviews/{msg}/export?format=pdf").status_code == 422
