"""DTOs for the agent settings admin surface (RAG `/admin/agent/*`).

Single source of truth for both the HTTP boundary and the persisted
`agent_settings.yaml` shape (same model serialised both ways). All generation
fields are optional: None means "do not send this param — use the model/server
default".
"""

from typing import Literal

from pydantic import BaseModel, Field

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
ToolChoice = Literal["auto", "required", "none"]


class GenerationSettings(BaseModel):
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(None, ge=1)
    seed: int | None = None
    reasoning_effort: ReasoningEffort | None = None
    # advanced (collapsed in the UI)
    top_k: int | None = Field(None, ge=0)
    frequency_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    presence_penalty: float | None = Field(None, ge=-2.0, le=2.0)


class BehaviorSettings(BaseModel):
    system_prompt_legal: str | None = None
    system_prompt_text: str | None = None
    max_tool_iterations: int = Field(8, ge=1, le=10)
    tool_choice: ToolChoice = "auto"
    history_window: int | None = Field(None, ge=0)


class RagSearchSettings(BaseModel):
    enabled: bool = True
    limit: int = Field(8, ge=1, le=50)
    min_score: float = Field(0.0, ge=0.0)


class FetchArticleSettings(BaseModel):
    enabled: bool = True


class ListActsSettings(BaseModel):
    enabled: bool = True


class DateCalcSettings(BaseModel):
    enabled: bool = True


class WebSearchSettings(BaseModel):
    enabled: bool = False
    max_results: int = Field(5, ge=1, le=20)


class WebFetchSettings(BaseModel):
    enabled: bool = False
    max_chars: int = Field(20000, ge=1000, le=100000)


class ToolsSettings(BaseModel):
    rag_search: RagSearchSettings = RagSearchSettings()
    fetch_article: FetchArticleSettings = FetchArticleSettings()
    list_acts: ListActsSettings = ListActsSettings()
    date_calculator: DateCalcSettings = DateCalcSettings()
    web_search: WebSearchSettings = WebSearchSettings()
    web_fetch: WebFetchSettings = WebFetchSettings()


class ReviewSettings(BaseModel):
    """Contract-review pipeline overrides. None = not set (fall through to
    env / built-in default, see agent/api/deps.py)."""

    model: str | None = None
    concurrency: int | None = Field(None, ge=1, le=12)


class AgentSettings(BaseModel):
    model: str = "qwen/qwen3.6-flash"
    generation: GenerationSettings = GenerationSettings()
    behavior: BehaviorSettings = BehaviorSettings()
    tools: ToolsSettings = ToolsSettings()
    review: ReviewSettings = ReviewSettings()


class OpenRouterModel(BaseModel):
    id: str
    name: str
    context_length: int | None = None
    prompt_price: str | None = None  # USD per token, as returned by OpenRouter
    completion_price: str | None = None
    supports_tools: bool = False


class OpenRouterModelsResponse(BaseModel):
    models: list[OpenRouterModel]


class AgentPromptDefaults(BaseModel):
    """Built-in default system prompts, shown to the operator as placeholders."""

    system_prompt_legal: str
    system_prompt_text: str
