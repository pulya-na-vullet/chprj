"""Dump OpenAPI schemas for both ASGI apps into frontend/openapi/.

Requires DATABASE_URL to be set (via .env.local or environment) because
importing the app modules triggers pydantic-settings validation at module
level. No database connection is actually made.

Run via: ``uv run python -m scripts.generate_openapi``
Frontend TS generation reads from these files.
"""

import json
from pathlib import Path

from neurolegal.agent.api.app import app as agent_app
from neurolegal.documents.api.app import app as documents_app
from neurolegal.rag.api.app import app as rag_app
from neurolegal.templates.api.app import app as templates_app

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "openapi"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "rag.json").write_text(
        json.dumps(rag_app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "agent.json").write_text(
        json.dumps(agent_app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "documents.json").write_text(
        json.dumps(documents_app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "templates.json").write_text(
        json.dumps(templates_app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_DIR / 'rag.json'}")
    print(f"wrote {OUT_DIR / 'agent.json'}")
    print(f"wrote {OUT_DIR / 'documents.json'}")
    print(f"wrote {OUT_DIR / 'templates.json'}")


if __name__ == "__main__":
    main()
