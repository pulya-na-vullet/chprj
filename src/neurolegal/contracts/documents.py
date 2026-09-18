"""Client-facing DTOs for the risk-review playbook catalog."""

from pydantic import BaseModel, Field


class PlaybookInfo(BaseModel):
    id: str
    name: str
    rules_count: int
    # T-0048: варианты роли стороны для формы «Новая проверка» (из
    # playbook.roles); пустой список — плейбук ролей не объявил.
    roles: list[str] = Field(default_factory=list)


class PlaybooksResponse(BaseModel):
    playbooks: list[PlaybookInfo]
