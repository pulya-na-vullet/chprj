"""Admin routes for agent settings: read/write persisted config + model catalog.

Lives on the RAG service (same gating/SPA as other admin routes). Writes
`agent_settings.yaml`; the agent process reads it at startup. The catalog proxy
keeps the OpenRouter API key server-side.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurolegal.contracts import (
    AgentPromptDefaults,
    AgentSettings,
    OkResponse,
    OpenRouterModelsResponse,
)
from neurolegal.core.agent_prompts import DEFAULT_SYSTEM_PROMPT_LEGAL, DEFAULT_SYSTEM_PROMPT_TEXT
from neurolegal.core.agent_settings import load_agent_settings, save_agent_settings
from neurolegal.rag.api.deps import get_agent_settings_path
from neurolegal.rag.openrouter_models import fetch_models

router = APIRouter(prefix="/admin/agent")

_SettingsPath = Annotated[Path, Depends(get_agent_settings_path)]


@router.get("/settings", response_model=AgentSettings)
async def get_settings(path: _SettingsPath) -> AgentSettings:
    return load_agent_settings(path)


@router.put("/settings", response_model=OkResponse)
async def put_settings(req: AgentSettings, path: _SettingsPath) -> OkResponse:
    save_agent_settings(req, path)
    return OkResponse()


@router.get("/defaults", response_model=AgentPromptDefaults)
async def get_defaults() -> AgentPromptDefaults:
    return AgentPromptDefaults(
        system_prompt_legal=DEFAULT_SYSTEM_PROMPT_LEGAL,
        system_prompt_text=DEFAULT_SYSTEM_PROMPT_TEXT,
    )


@router.get("/models", response_model=OpenRouterModelsResponse)
async def get_models() -> OpenRouterModelsResponse:
    try:
        models = await fetch_models()
    except Exception as exc:  # surface upstream failure as 502
        raise HTTPException(status_code=502, detail=f"OpenRouter catalog failed: {exc}") from exc
    return OpenRouterModelsResponse(models=models)
