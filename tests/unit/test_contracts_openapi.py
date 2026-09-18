"""OpenAPI snapshot guard.

If a route or DTO changes, this test fails and prints the diff. To accept the
change after verifying it's intentional:

  uv run python -m scripts.generate_openapi
  cp frontend/openapi/rag.json       tests/data/openapi/rag.json
  cp frontend/openapi/agent.json     tests/data/openapi/agent.json
  cp frontend/openapi/documents.json tests/data/openapi/documents.json
  cp frontend/openapi/templates.json tests/data/openapi/templates.json
  npm --prefix frontend run openapi:generate

Then commit the snapshots, the regenerated TS types, and the changed API code
together so the backend schema, the TS types, and this snapshot move as one.
(All four snapshots are guarded here; `openapi:generate` builds TS only for
rag+agent — documents.json and templates.json are snapshot gates, not TS
sources: the browser talks to the hub and the templates service only through
the agent's proxy routes.)"""

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO / "tests" / "data" / "openapi"
LIVE_DIR = REPO / "frontend" / "openapi"


@pytest.fixture(scope="module", autouse=True)
def _live_schemas() -> None:
    """Regenerate `frontend/openapi/{rag,agent}.json` once per module run.

    Spawning `uv run` once instead of per-parametrize-variant keeps the test
    fast. Failures surface both stdout and stderr so a broken generate script
    is obvious in CI logs."""
    result = subprocess.run(
        ["uv", "run", "python", "-m", "scripts.generate_openapi"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "scripts.generate_openapi failed "
            f"(exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


@pytest.mark.parametrize("name", ["rag.json", "agent.json", "documents.json", "templates.json"])
def test_openapi_matches_snapshot(name: str) -> None:
    snapshot_path = SNAPSHOT_DIR / name
    live_path = LIVE_DIR / name
    assert snapshot_path.exists(), (
        f"missing snapshot {snapshot_path}. "
        f"Generate one with `uv run python -m scripts.generate_openapi` "
        f"and copy frontend/openapi/{name} → tests/data/openapi/{name}."
    )
    live = json.loads(live_path.read_text(encoding="utf-8"))
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert live == snap, (
        f"OpenAPI for {name} drifted. Diff:\n"
        f"  diff {snapshot_path} {live_path}\n"
        f"To accept the change, run:\n"
        f"  uv run python -m scripts.generate_openapi\n"
        f"  cp {live_path} {snapshot_path}\n"
        f"  npm --prefix frontend run openapi:generate\n"
        f"and commit all changed files together."
    )
