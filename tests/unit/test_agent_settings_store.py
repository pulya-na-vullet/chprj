from neurolegal.contracts import AgentSettings, GenerationSettings
from neurolegal.core.agent_settings import load_agent_settings, save_agent_settings


def test_load_missing_returns_defaults(tmp_path):
    s = load_agent_settings(tmp_path / "nope.yaml")
    assert s == AgentSettings()


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "agent_settings.yaml"
    original = AgentSettings(model="a/b", generation=GenerationSettings(temperature=0.5))
    save_agent_settings(original, path)
    assert path.exists()
    loaded = load_agent_settings(path)
    assert loaded.model == "a/b"
    assert loaded.generation.temperature == 0.5


def test_save_is_atomic_no_tmp_left(tmp_path):
    path = tmp_path / "agent_settings.yaml"
    save_agent_settings(AgentSettings(), path)
    assert not (tmp_path / "agent_settings.yaml.tmp").exists()
