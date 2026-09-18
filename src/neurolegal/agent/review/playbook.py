"""Плейбук проверки договора: Pydantic-модели и загрузчик YAML."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class PlaybookError(Exception):
    pass


class PlaybookRule(BaseModel):
    id: str
    title: str
    question: str
    anchors: list[str] = Field(default_factory=list)
    risk_if_missing: Literal["high", "medium", "low"] | None = None
    law_hints: list[str] = Field(default_factory=list)
    rag_queries: list[str] = Field(default_factory=list)


class Playbook(BaseModel):
    id: str
    name: str
    roles: list[str] = Field(default_factory=list)
    doc_kind: Literal["contract", "service_doc"] = "contract"
    rules: list[PlaybookRule] = Field(min_length=1)

    @field_validator("rules")
    @classmethod
    def _unique_rule_ids(cls, v: list[PlaybookRule]) -> list[PlaybookRule]:
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rule ids")
        return v


def load_playbooks(directory: Path) -> dict[str, Playbook]:
    result: dict[str, Playbook] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            pb = Playbook.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise PlaybookError(f"{path.name}: {exc}") from exc
        if pb.id in result:
            raise PlaybookError(f"duplicate playbook id: {pb.id}")
        result[pb.id] = pb
    return result
