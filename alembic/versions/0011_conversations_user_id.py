"""wipe dev data + conversations.user_id

Request-scoping cutover (T-0021, design doc 2026-07-11-auth-design §2). Wipes
dev-era conversations/messages/hub_documents (all pre-auth rows have no real
owner — the client's decision was to start clean rather than backfill), then
adds the NOT NULL `conversations.user_id` FK + index. Schema and scoping code
(ConversationStore, route gating) switch atomically in this same task so the
column is never nullable/defaulted.

`hub_documents` deletion cascades to `hub_document_attachments` via its FK
(ondelete=CASCADE) — no explicit DELETE needed for that table. Orphaned S3
objects under `owner/default/...` are cleaned up separately (out of band, see
design doc §2.5) — not this migration's concern.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM messages")
    op.execute("DELETE FROM conversations")
    op.execute("DELETE FROM hub_documents")
    op.add_column("conversations", sa.Column("user_id", sa.String(length=36), nullable=False))
    op.create_foreign_key(
        "conversations_user_id_fkey",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    # Best-effort: drops the column back off. Does not restore wiped data —
    # there is nothing to restore it from.
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_constraint("conversations_user_id_fkey", "conversations", type_="foreignkey")
    op.drop_column("conversations", "user_id")
