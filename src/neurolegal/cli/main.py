"""Top-level Neurolegal CLI dispatcher.

Usage:
    neurolegal migrate
    neurolegal rag ingest --code X [--bulk]
    neurolegal rag search "..."
    neurolegal agent chat

Each subgroup lives in its own module so the rag/agent boundary holds at
the command level too.
"""

import subprocess

import typer

from neurolegal.agent.cli import app as agent_app
from neurolegal.core.logging_setup import configure_logging
from neurolegal.rag.cli import app as rag_app

app = typer.Typer(no_args_is_help=True, help="Neurolegal backend CLI.")
app.add_typer(rag_app, name="rag")
app.add_typer(agent_app, name="agent")


@app.command()
def migrate() -> None:
    """Run alembic upgrade head against the current DATABASE_URL."""
    configure_logging()
    result = subprocess.run(["alembic", "upgrade", "head"], check=False)
    raise typer.Exit(code=result.returncode)


if __name__ == "__main__":
    app()
