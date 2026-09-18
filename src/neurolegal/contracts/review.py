"""DTOs for the "risk review" feature — playbook-driven contract review.

Imports `Citation` from `contracts.chat`, so `chat.py` must not import this
module at runtime (it would cycle). `chat.py` refers to `ReviewReportData`
only under `TYPE_CHECKING`, as a string annotation on `MessageOut.review`;
`contracts/__init__.py` calls `MessageOut.model_rebuild()` after both modules
are imported to resolve that forward reference."""

from typing import Literal

from pydantic import BaseModel

from neurolegal.contracts.chat import Citation

RiskLevel = Literal["high", "medium", "low"]
CoverageStatus = Literal["ok", "risk", "missing", "not_applicable"]
Verdict = Literal["confirmed", "overstated", "not_a_risk"]


class ReviewRisk(BaseModel):
    rule_id: str
    title: str
    level: RiskLevel
    verdict: Verdict
    section_number: str | None = None
    contract_quote: str
    explanation: str
    recommendation: str
    citations: list[Citation] = []
    no_basis: bool = False


class ReviewCoverageItem(BaseModel):
    rule_id: str
    title: str
    status: CoverageStatus


class ReviewReportData(BaseModel):
    playbook_id: str
    playbook_name: str
    document_id: str
    risks: list[ReviewRisk]
    coverage: list[ReviewCoverageItem]
    disclaimer: str
    role: str | None = None
    # T-0047: короткое деловое резюме отчёта («что в целом по договору»,
    # LLM-вызов в конце пайплайна). None — резюме не построилось (сбой
    # вызова) или отчёт старый.
    summary: str | None = None


class ReviewProgressEventData(BaseModel):
    rule_id: str
    title: str
    index: int
    total: int
    status: CoverageStatus | Literal["running"]


class ReviewReportEventData(ReviewReportData):
    pass
