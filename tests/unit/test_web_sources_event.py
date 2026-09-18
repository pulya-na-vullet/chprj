from neurolegal.agent.chat.events import WebSourcesEvent


def test_web_sources_event_data() -> None:
    ev = WebSourcesEvent(sources=[{"url": "https://e.gov", "title": "T", "snippet": "s"}])
    assert ev.event == "web_sources"
    assert ev.data["sources"][0]["url"] == "https://e.gov"
