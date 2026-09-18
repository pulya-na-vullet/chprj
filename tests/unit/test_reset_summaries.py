"""T-0147 Minor 16 (финальное ревью): подтверждение --yes и точный rowcount
для scripts/reset_summaries.py."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import reset_summaries


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


def _fake_engine(scalar_value: int, exec_result: Any = None) -> tuple[MagicMock, AsyncMock]:
    conn = AsyncMock()
    conn.scalar = AsyncMock(return_value=scalar_value)
    conn.execute = AsyncMock(return_value=exec_result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin = MagicMock(return_value=ctx)
    engine.dispose = AsyncMock()
    return engine, conn


@pytest.mark.asyncio
async def test_without_yes_refuses_and_does_not_update(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, conn = _fake_engine(scalar_value=5)
    monkeypatch.setattr(reset_summaries, "get_engine", lambda: engine)

    with pytest.raises(SystemExit):
        await reset_summaries.main_async(dry_run=False, yes=False)

    conn.execute.assert_not_called()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_yes_runs_update_and_prints_actual_rowcount(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # count(*) видит 5 строк, но фактически UPDATE трогает 3 (надмножество,
    # включая уже-NULL) — печатаем именно rowcount, не предварительный count.
    engine, conn = _fake_engine(scalar_value=5, exec_result=_FakeResult(rowcount=3))
    monkeypatch.setattr(reset_summaries, "get_engine", lambda: engine)

    await reset_summaries.main_async(dry_run=False, yes=True)

    conn.execute.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    assert "обнулено строк: 3" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_dry_run_does_not_require_yes_and_does_not_update(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, conn = _fake_engine(scalar_value=7)
    monkeypatch.setattr(reset_summaries, "get_engine", lambda: engine)

    await reset_summaries.main_async(dry_run=True, yes=False)

    conn.execute.assert_not_called()
    assert "dry-run: обнулило бы 7 строк" in capsys.readouterr().out
