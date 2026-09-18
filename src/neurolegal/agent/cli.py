"""Agent CLI."""

import asyncio
import json
from typing import Annotated

import typer

from neurolegal.agent.eval.benchmark import DEFAULT_CASES, score_case, summarize
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.core.logging_setup import configure_logging

app = typer.Typer(no_args_is_help=True, help="Neurolegal agent CLI.")


@app.command()
def chat() -> None:
    """Start an interactive chat session (not yet implemented)."""
    configure_logging()
    typer.echo("agent chat: not yet implemented", err=True)
    raise typer.Exit(code=2)


@app.command("eval-retrieval")
def eval_retrieval(
    base_url: Annotated[
        str,
        typer.Option("--rag-url", help="Base URL of the RAG service."),
    ] = "http://127.0.0.1:8001",
    limit: Annotated[int, typer.Option("--limit", min=1, max=50)] = 8,
    case_id: Annotated[
        str | None,
        typer.Option("--case", help="Run a single benchmark case by id."),
    ] = None,
) -> None:
    """Run the seed retrieval benchmark against a live RAG service."""
    configure_logging()

    async def run() -> None:
        client = RagClient(base_url=base_url)
        cases = [case for case in DEFAULT_CASES if case_id is None or case.id == case_id]
        if not cases:
            typer.echo(f"unknown benchmark case: {case_id}", err=True)
            raise typer.Exit(code=2)
        scores = []
        for case in cases:
            articles = await client.search(case.question, limit=limit)
            scores.append(score_case(case, articles))
        report = summarize(scores)
        typer.echo(
            json.dumps(
                {
                    "citation_recall": report.citation_recall,
                    "act_recall": report.act_recall,
                    "mrr": report.mrr,
                    "top_score_avg": report.top_score_avg,
                    "cases": [
                        {
                            "id": score.case_id,
                            "question": score.question,
                            "citation_recall": score.citation_recall,
                            "act_recall": score.act_recall,
                            "reciprocal_rank": score.reciprocal_rank,
                            "expected": [
                                {"act": c.act_short_name, "number": c.number}
                                for c in score.expected
                            ],
                            "found": [
                                {"act": c.act_short_name, "number": c.number}
                                for c in score.found[:5]
                            ],
                        }
                        for score in report.cases
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    asyncio.run(run())


if __name__ == "__main__":
    app()
