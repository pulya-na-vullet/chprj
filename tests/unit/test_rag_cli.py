"""Unit tests for the ``neurolegal rag`` CLI commands.

The commands wire real infrastructure (DB sessionmaker, embedder, ingest
pipeline). Here everything external is mocked so the tests stay offline and
never touch a database — they assert the *command wiring*, in particular the
``--bulk`` drop/recreate-index ``try/finally`` that is operationally
load-bearing (see CLAUDE.md "HNSW index maintenance").
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from neurolegal.rag import cli

runner = CliRunner()


class _FakeSessionCM:
    """Minimal async context manager standing in for ``session_factory()``."""

    async def __aenter__(self) -> MagicMock:
        return MagicMock()

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    order: list[str] = []

    def _run(code: str) -> SimpleNamespace:
        order.append("run")
        return SimpleNamespace(act_id="A1", articles_count=3, chunks_count=9)

    pipeline = MagicMock()
    pipeline.run = AsyncMock(side_effect=_run)
    session_factory = MagicMock(side_effect=lambda: _FakeSessionCM())
    drop = AsyncMock(side_effect=lambda *a: order.append("drop"))
    create = AsyncMock(side_effect=lambda *a: order.append("create"))

    monkeypatch.setattr(cli, "load_manifest", MagicMock(return_value=object()))
    monkeypatch.setattr(cli, "make_embedder", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(cli, "get_sessionmaker", MagicMock(return_value=session_factory))
    monkeypatch.setattr(cli, "build_pipeline", MagicMock(return_value=pipeline))
    monkeypatch.setattr(cli, "drop_search_indexes", drop)
    monkeypatch.setattr(cli, "create_search_indexes", create)
    return SimpleNamespace(pipeline=pipeline, drop=drop, create=create, order=order)


def test_ingest_runs_pipeline_per_code_without_bulk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _patch_common(monkeypatch)
    result = runner.invoke(cli.app, ["ingest", "--code", "ГК-1", "--code", "ВК"])
    assert result.exit_code == 0, result.output
    assert m.pipeline.run.await_count == 2
    m.drop.assert_not_awaited()
    m.create.assert_not_awaited()
    payloads = [
        json.loads(line) for line in result.output.splitlines() if line.strip().startswith("{")
    ]
    assert {p["code"] for p in payloads} == {"ГК-1", "ВК"}


def test_ingest_bulk_drops_then_recreates_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _patch_common(monkeypatch)
    result = runner.invoke(cli.app, ["ingest", "--code", "ГК-1", "--bulk"])
    assert result.exit_code == 0, result.output
    m.drop.assert_awaited_once()
    m.create.assert_awaited_once()
    assert m.order == ["drop", "run", "create"]


def test_ingest_bulk_recreates_indexes_even_when_pipeline_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _patch_common(monkeypatch)
    m.pipeline.run.side_effect = RuntimeError("boom")
    result = runner.invoke(cli.app, ["ingest", "--code", "ГК-1", "--bulk"])
    assert result.exit_code != 0
    m.drop.assert_awaited_once()
    # The finally branch must recreate the indexes despite the failure.
    m.create.assert_awaited_once()


def test_reindex_runs_pipeline_once_without_touching_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _patch_common(monkeypatch)
    result = runner.invoke(cli.app, ["reindex", "--code", "ГК-1"])
    assert result.exit_code == 0, result.output
    m.pipeline.run.assert_awaited_once_with("ГК-1")
    m.drop.assert_not_awaited()
    m.create.assert_not_awaited()


def test_search_forwards_args_and_prints_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = MagicMock()
    article.model_dump.return_value = {"number": "1477", "score": 0.9}
    svc = MagicMock()
    svc.search = AsyncMock(return_value=[article])
    session_factory = MagicMock(side_effect=lambda: _FakeSessionCM())

    monkeypatch.setattr(cli, "make_embedder", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(cli, "RetrievalService", MagicMock(return_value=svc))
    monkeypatch.setattr(cli, "get_sessionmaker", MagicMock(return_value=session_factory))

    result = runner.invoke(cli.app, ["search", "товарный знак", "--act", "ГК РФ", "--limit", "3"])
    assert result.exit_code == 0, result.output
    svc.search.assert_awaited_once()
    args, kwargs = svc.search.call_args
    assert args[1] == "товарный знак"
    assert kwargs["acts"] == ["ГК РФ"]
    assert kwargs["limit"] == 3
    assert "1477" in result.output


def test_indexes_status_prints_presence(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = MagicMock(side_effect=lambda: _FakeSessionCM())
    inspect = AsyncMock(
        return_value={
            "chunks_embedding_hnsw": True,
            "chunks_search_vector_gin": False,
        }
    )
    monkeypatch.setattr(cli, "get_sessionmaker", MagicMock(return_value=session_factory))
    monkeypatch.setattr(cli, "inspect_search_indexes", inspect, raising=False)

    result = runner.invoke(cli.app, ["indexes", "status"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {
        "chunks_embedding_hnsw": True,
        "chunks_search_vector_gin": False,
    }


def test_indexes_drop_calls_drop_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = MagicMock(side_effect=lambda: _FakeSessionCM())
    drop = AsyncMock()
    monkeypatch.setattr(cli, "get_sessionmaker", MagicMock(return_value=session_factory))
    monkeypatch.setattr(cli, "drop_search_indexes", drop)

    result = runner.invoke(cli.app, ["indexes", "drop"])
    assert result.exit_code == 0, result.output
    assert drop.await_count == 1


def test_indexes_create_calls_create_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = MagicMock(side_effect=lambda: _FakeSessionCM())
    create = AsyncMock()
    monkeypatch.setattr(cli, "get_sessionmaker", MagicMock(return_value=session_factory))
    monkeypatch.setattr(cli, "create_search_indexes", create)

    result = runner.invoke(cli.app, ["indexes", "create"])
    assert result.exit_code == 0, result.output
    assert create.await_count == 1
