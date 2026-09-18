from neurolegal.agent.chat.events import AskEvent, DoneEvent, ResetDeltaEvent, ToolResultEvent


def test_ask_event_data_shape() -> None:
    ev = AskEvent(question="Кто вы по этому договору?", options=["Заказчик", "Исполнитель"])
    assert ev.event == "ask"
    assert ev.data == {
        "question": "Кто вы по этому договору?",
        "options": ["Заказчик", "Исполнитель"],
        "allow_free_text": True,
        "kind": "review_role",
        "template": False,
    }


def test_ask_event_allow_free_text_override() -> None:
    ev = AskEvent(question="q", options=[], allow_free_text=False)
    assert ev.data == {
        "question": "q",
        "options": [],
        "allow_free_text": False,
        "kind": "review_role",
        "template": False,
    }


def test_tool_result_event_data_shape() -> None:
    ev = ToolResultEvent(found=[{"act": "ГК РФ", "number": "1477"}])
    assert ev.event == "tool_result"
    assert ev.data == {"found": [{"act": "ГК РФ", "number": "1477"}]}


def test_reset_delta_event() -> None:
    ev = ResetDeltaEvent()
    assert ev.event == "reset_delta"
    assert ev.data == {}


def test_done_event_stopped_payload() -> None:
    ev = DoneEvent(message_id=None, stopped=True)
    assert ev.data == {"message_id": None, "stopped": True}


def test_done_event_default_not_stopped() -> None:
    ev = DoneEvent(message_id="m1")
    assert ev.data == {"message_id": "m1", "stopped": False}


def test_ask_event_carries_kind() -> None:
    ev = AskEvent(question="Кто вы?", options=["А", "Б"], kind="ask_user")
    assert ev.event == "ask"
    assert ev.data["kind"] == "ask_user"


def test_ask_event_kind_defaults_to_review_role() -> None:
    ev = AskEvent(question="Кто вы по договору?", options=[])
    assert ev.data["kind"] == "review_role"
