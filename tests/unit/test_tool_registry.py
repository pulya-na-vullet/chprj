from neurolegal.agent.chat.tools.registry import build_registry
from neurolegal.contracts import ToolsSettings


def test_registry_includes_enabled_only() -> None:
    s = ToolsSettings()
    s.rag_search.enabled = True
    s.web_search.enabled = False
    reg = build_registry(s)
    assert "rag_search" in reg
    assert "web_search" not in reg


def test_registry_specs_match_keys() -> None:
    s = ToolsSettings()
    for f in (s.web_search, s.web_fetch):
        f.enabled = True
    reg = build_registry(s)
    for name, (spec, _handler) in reg.items():
        assert spec.name == name
