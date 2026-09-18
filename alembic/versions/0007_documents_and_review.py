"""documents table + messages.review

Creates the agent-owned ``documents`` table (uploaded contract documents,
parsed into sections + full text, one per conversation) and adds a
``review`` JSON column to ``messages`` for storing the structured contract
review result attached to an assistant message. Matches the SQLite-portable
models in neurolegal.agent.store.models. Independent of the rag schema.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("mime", sa.String(), nullable=False),
        sa.Column("parser", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="documents_conversation_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="documents_pkey"),
    )
    op.create_index("ix_documents_conversation_id", "documents", ["conversation_id"])
    op.add_column("messages", sa.Column("review", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "review")
    op.drop_index("ix_documents_conversation_id", table_name="documents")
    op.drop_table("documents")
