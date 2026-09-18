"""Unit test for the ``neurolegal agent chat`` CLI (a stub).

Invoked through the top-level dispatcher (``neurolegal agent chat``) — the real
path users take. Invoking the agent sub-app directly with ``["chat"]`` would
collapse the single-command Typer into a usage error (also exit 2), so going
through the dispatcher is what actually exercises the stub body.
"""

from typer.testing import CliRunner

from neurolegal.cli.main import app as main_app
from neurolegal.contracts import SearchedArticle

runner = CliRunner()


def test_agent_chat_is_a_stub_exiting_with_code_2() -> None:
    result = runner.invoke(main_app, ["agent", "chat"])
    assert result.exit_code == 2
    assert "not yet implemented" in result.output


def test_agent_eval_retrieval_prints_metrics(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _FakeRagClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        async def search(self, query: str, *, limit: int = 8, **kwargs):  # type: ignore[no-untyped-def]
            return [
                SearchedArticle(
                    article_id="00000000-0000-0000-0000-000000000001",
                    act_short_name="ВК РФ",
                    act_kind="codex",
                    number="3",
                    title="Основные принципы водного законодательства",
                    full_text="текст",
                    matched_chunks=[],
                    score=0.2,
                )
            ]

    monkeypatch.setattr("neurolegal.agent.cli.RagClient", _FakeRagClient)

    result = runner.invoke(
        main_app,
        ["agent", "eval-retrieval", "--case", "water-principles", "--rag-url", "http://rag"],
    )

    assert result.exit_code == 0
    assert '"citation_recall": 1.0' in result.output
    assert '"mrr": 1.0' in result.output
    assert '"water-principles"' in result.output
