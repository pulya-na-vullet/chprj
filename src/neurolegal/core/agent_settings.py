"""Atomic load/save for the persisted agent settings (`agent_settings.yaml`).

Mirrors the manifest pattern in `rag/acquisition/manifest.py`: write to a temp
file then `os.replace`. A missing file yields defaults so a fresh deploy works
before the operator saves anything.
"""

import os
from pathlib import Path

import yaml

from neurolegal.contracts import AgentSettings


def load_agent_settings(path: Path) -> AgentSettings:
    if not path.exists():
        return AgentSettings()
    raw = yaml.safe_load(path.read_text("utf-8")) or {}
    if "rag_search" in raw and "rag_search" not in raw.get("tools", {}):
        raw.setdefault("tools", {})["rag_search"] = raw.pop("rag_search")
    return AgentSettings.model_validate(raw)


def save_agent_settings(settings: AgentSettings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        yaml.safe_dump(settings.model_dump(), allow_unicode=True, sort_keys=False),
        "utf-8",
    )
    os.replace(tmp, path)
