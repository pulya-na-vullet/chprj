"""Unit tests for the top-level ``neurolegal`` CLI dispatcher (``migrate``)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from neurolegal.cli import main

runner = CliRunner()


def test_migrate_runs_alembic_upgrade_head() -> None:
    with patch.object(main.subprocess, "run", return_value=MagicMock(returncode=0)) as run:
        result = runner.invoke(main.app, ["migrate"])
    assert result.exit_code == 0
    run.assert_called_once_with(["alembic", "upgrade", "head"], check=False)


def test_migrate_propagates_nonzero_exit_code() -> None:
    with patch.object(main.subprocess, "run", return_value=MagicMock(returncode=3)):
        result = runner.invoke(main.app, ["migrate"])
    assert result.exit_code == 3
