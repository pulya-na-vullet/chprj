"""Unit tests for date_calculator tool — no network, all working-day calls monkeypatched."""

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.chat.tools.date_calculator import handle
from neurolegal.contracts import ToolsSettings

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


class _FakeRag:
    """Minimal stub; date_calculator never calls rag_client."""


def _ctx() -> ToolContext:
    return ToolContext(
        rag_client=_FakeRag(),  # type: ignore[arg-type]
        acts=None,
        tools=ToolsSettings(),
    )


def _result(outcome: ToolOutcome) -> Any:
    return json.loads(outcome.tool_result)


# ---------------------------------------------------------------------------
# Basic arithmetic ops (no working-day calls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_days() -> None:
    outcome = await handle({"op": "add_days", "date": "2026-01-10", "days": 5}, _ctx())
    data = _result(outcome)
    assert data["result"] == "2026-01-15"


@pytest.mark.asyncio
async def test_diff_days() -> None:
    outcome = await handle({"op": "diff_days", "date": "2026-01-10", "date2": "2026-01-15"}, _ctx())
    data = _result(outcome)
    assert data["result"] == 5


@pytest.mark.asyncio
async def test_weekday() -> None:
    # 2026-06-12 is a Friday → ISO weekday 5
    outcome = await handle({"op": "weekday", "date": "2026-06-12"}, _ctx())
    data = _result(outcome)
    assert data["result"] == 5


@pytest.mark.asyncio
async def test_invalid_date() -> None:
    outcome = await handle({"op": "add_days", "date": "not-a-date"}, _ctx())
    data = _result(outcome)
    assert "error" in data


# ---------------------------------------------------------------------------
# Working-day ops — is_working_day monkeypatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_working_day() -> None:
    # Monkeypatch returns (True, False) — is_working=True, no fallback
    with patch(
        "neurolegal.agent.chat.tools.date_calculator.is_working_day",
        new=AsyncMock(return_value=(True, False)),
    ):
        outcome = await handle({"op": "is_working_day", "date": "2026-06-12"}, _ctx())
    data = _result(outcome)
    assert data["result"] is True
    assert "fallback" not in data


@pytest.mark.asyncio
async def test_add_working_days() -> None:
    """2026-06-12 (Fri) + 1 working day → skip Sat+Sun → 2026-06-15 (Mon)."""

    async def _fake_is_working_day(d: date) -> tuple[bool, bool]:
        return (d.weekday() < 5, False)  # Mon-Fri = working, no fallback

    with patch(
        "neurolegal.agent.chat.tools.date_calculator.is_working_day",
        new=_fake_is_working_day,
    ):
        outcome = await handle({"op": "add_working_days", "date": "2026-06-12", "days": 1}, _ctx())
    data = _result(outcome)
    assert data["result"] == "2026-06-15"
    assert "fallback" not in data


@pytest.mark.asyncio
async def test_fallback_flag() -> None:
    """When is_working_day returns fallback=True the output must contain fallback:true."""

    async def _fake_is_working_day(d: date) -> tuple[bool, bool]:
        return (d.weekday() < 5, True)  # Mon-Fri heuristic, always fallback

    with patch(
        "neurolegal.agent.chat.tools.date_calculator.is_working_day",
        new=_fake_is_working_day,
    ):
        outcome = await handle({"op": "add_working_days", "date": "2026-06-12", "days": 1}, _ctx())
    data = _result(outcome)
    assert data.get("fallback") is True
