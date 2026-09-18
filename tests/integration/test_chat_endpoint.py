"""End-to-end /chat test. Opt-in: needs a live DATABASE_URL with migrations
applied (alembic upgrade head) and OPENROUTER_API_KEY.

T-0103: этот файл остаётся ручной предрелизной проверкой на ЖИВОЙ модели —
он единственный отвечает на вопрос «настоящая LLM ведёт себя как ожидается».
При этом контракт SSE (порядок и состав кадров) больше не держится на нём:
tests/integration/test_chat_sse_contract.py проверяет тот же контракт на
замоканной модели под маркером api_with_mocks и выполняется в обычном прогоне.

Run with: uv run pytest tests/integration/test_chat_endpoint.py -m e2e
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from neurolegal.agent.api.app import app

pytestmark = pytest.mark.e2e


@pytest.mark.skipif(
    not (os.getenv("DATABASE_URL") and os.getenv("OPENROUTER_API_KEY")),
    reason="needs DATABASE_URL and OPENROUTER_API_KEY",
)
def test_chat_end_to_end() -> None:
    # Both turns share one TestClient on purpose: each `with TestClient(app)`
    # spawns its own event loop, but the module-level engine cache in
    # neurolegal.core.db keeps asyncpg connections from the previous loop. Reusing
    # the same client keeps the loop alive across both POSTs and prevents
    # "Event loop is closed" failures during pool teardown.
    with TestClient(app) as tc:
        resp = tc.post(
            "/chat",
            json={
                "session_id": None,
                "message": "Какие основные принципы водного законодательства?",
            },
        )
        assert resp.status_code == 200

        names: list[str] = []
        session_id: str | None = None
        for line in resp.text.splitlines():
            if line.startswith("event:"):
                names.append(line[len("event:") :].strip())
            elif line.startswith("data:") and session_id is None and names == ["session"]:
                session_id = json.loads(line[len("data:") :].strip())["session_id"]

        assert names[0] == "session"
        assert names[-1] == "done"
        assert "citations" in names
        assert session_id is not None

        # Second turn on the same conversation must not re-emit `session`.
        resp2 = tc.post(
            "/chat",
            json={"session_id": session_id, "message": "А кто их устанавливает?"},
        )
        assert resp2.status_code == 200
        names2 = [
            line[len("event:") :].strip()
            for line in resp2.text.splitlines()
            if line.startswith("event:")
        ]
        assert "session" not in names2
        assert names2[-1] == "done"
