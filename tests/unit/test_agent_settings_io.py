from pathlib import Path

from neurolegal.contracts import AgentSettings
from neurolegal.core.agent_settings import load_agent_settings, save_agent_settings


def test_loads_legacy_top_level_rag_search(tmp_path: Path) -> None:
    p = tmp_path / "agent_settings.yaml"
    p.write_text("rag_search:\n  enabled: false\n  limit: 5\n", "utf-8")
    s = load_agent_settings(p)
    assert s.tools.rag_search.enabled is False
    assert s.tools.rag_search.limit == 5


def test_new_shape_round_trips(tmp_path: Path) -> None:
    p = tmp_path / "agent_settings.yaml"
    s = AgentSettings()
    s.tools.web_search.enabled = True
    save_agent_settings(s, p)
    loaded = load_agent_settings(p)
    assert loaded.tools.web_search.enabled is True
    head = p.read_text("utf-8").split("tools:")[0]
    assert "rag_search" not in head
