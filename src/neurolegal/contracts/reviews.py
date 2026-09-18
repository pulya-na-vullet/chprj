"""DTOs for the reviews index — the «Проверки» section (T-0048).

`GET /reviews` returns a per-user digest of risk-review runs assembled from
`messages.review` (done) and `messages.ask` with kind="review_failed"
(failed). Document name/type come from the documents hub and are nullable:
the run stays listed after its document is deleted from the library.
"""

from typing import Literal

from pydantic import BaseModel


class ReviewListItem(BaseModel):
    message_id: str
    conversation_id: str
    playbook_id: str
    playbook_name: str
    document_id: str
    document_filename: str | None = None
    document_parser: str | None = None
    role: str | None = None
    status: Literal["done", "failed"]
    high: int = 0
    medium: int = 0
    low: int = 0
    rules_total: int = 0
    error: str | None = None
    created_at: str


class ReviewsResponse(BaseModel):
    items: list[ReviewListItem]
    total: int
