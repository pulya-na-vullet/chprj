from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.chat.intent import Intent
from neurolegal.agent.llm.types import TextChunk
from neurolegal.contracts import BehaviorSettings, RagSearchSettings, ToolsSettings


class _FakeLLM:
    def __init__(self):
        self.seen_system = None
        self.seen_tools = None

    async def stream(self, messages, tools):
        self.seen_system = messages[0].content
        self.seen_tools = tools
        yield TextChunk(text="ok")


USER_ID = "u1"


class _FakeStore:
    async def load_history(self, _conversation_id, _user_id):
        return []

    async def get_template_draft(self, _conversation_id):
        return None

    async def append_message(self, *a, **k):
        return "msg-1"

    async def commit(self):
        pass

    async def last_message(self, _conversation_id, _user_id):
        return None


async def test_custom_legal_prompt_used():
    llm = _FakeLLM()
    agent = ChatAgent(
        llm=llm,
        rag_client=object(),
        store=_FakeStore(),
        behavior=BehaviorSettings(system_prompt_legal="КАСТОМ"),
        classify_intent=lambda _: Intent.LEGAL,
    )
    async for _ in agent.run("c1", "вопрос", user_id=USER_ID):
        pass
    # T-0051: LEGAL turns append ASK_USER_NOTE after the (possibly custom)
    # system prompt, so the custom prompt is a prefix, not the whole string.
    assert llm.seen_system is not None and llm.seen_system.startswith("КАСТОМ")


async def test_rag_search_disabled_removes_tool():
    """When rag_search is disabled in ToolsSettings, its spec must not be
    passed to the LLM. Other tools may still be present."""
    llm = _FakeLLM()
    agent = ChatAgent(
        llm=llm,
        rag_client=object(),
        store=_FakeStore(),
        tools=ToolsSettings(rag_search=RagSearchSettings(enabled=False)),
        classify_intent=lambda _: Intent.LEGAL,
    )
    async for _ in agent.run("c1", "вопрос", user_id=USER_ID):
        pass
    assert all(t.name != "rag_search" for t in llm.seen_tools)


async def test_non_legal_intent_receives_no_research_tools():
    """TEXT_TASK gets no RAG/registry tools — only ask_user (T-0051), which
    every non-smalltalk intent sees regardless of registry contents."""
    llm = _FakeLLM()
    agent = ChatAgent(
        llm=llm,
        rag_client=object(),
        store=_FakeStore(),
        classify_intent=lambda _: Intent.TEXT_TASK,
    )
    async for _ in agent.run("c1", "Перефразируй текст", user_id=USER_ID):
        pass
    assert [t.name for t in llm.seen_tools] == ["ask_user"]


async def test_history_window_zero_sends_no_history():
    class _Msg:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

    class _StoreWithHistory:
        async def load_history(self, _conversation_id: str, _user_id: str) -> list[_Msg]:
            return [_Msg("user", "старое"), _Msg("assistant", "ответ")]

        async def get_template_draft(self, _conversation_id: str) -> None:
            return None

        async def append_message(self, *a: object, **k: object) -> str:
            return "msg-1"

        async def commit(self) -> None:
            pass

        async def last_message(self, _conversation_id: str, _user_id: str) -> None:
            return None

    captured: dict[str, list[str]] = {}

    class _CapLLM:
        async def stream(self, messages: list, tools: list):  # type: ignore[override]
            captured["roles"] = [m.role for m in messages]
            yield TextChunk(text="ok")

    agent = ChatAgent(
        llm=_CapLLM(),  # type: ignore[arg-type]
        rag_client=object(),  # type: ignore[arg-type]
        store=_StoreWithHistory(),  # type: ignore[arg-type]
        behavior=BehaviorSettings(history_window=0),
        classify_intent=lambda _: Intent.TEXT_TASK,
    )
    async for _ in agent.run("c1", "новый вопрос", user_id=USER_ID):
        pass
    # system + current user only — no replayed history
    assert captured["roles"] == ["system", "user"]
