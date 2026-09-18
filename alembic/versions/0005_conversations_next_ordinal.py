"""conversations.next_ordinal for atomic message-ordinal allocation

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-01

Adds ``next_ordinal`` column to ``conversations`` (default 0) and back-fills
existing rows so the column matches the current count of messages per
conversation. After this migration ``ConversationStore.append_message`` no
longer races on ``count(*)``; the per-row ``UPDATE … RETURNING`` allocates
ordinals atomically.

Migration is online-safe on Postgres: an ACCESS EXCLUSIVE table lock is
acquired before the ADD COLUMN to prevent concurrent inserts/updates from
observing the brief window between ADD COLUMN (server_default=0) and the
back-fill UPDATE. The lock is released at transaction commit. Concurrent
readers block briefly; concurrent writers block until the migration commits.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Take an EXCLUSIVE table lock so concurrent INSERT / UPDATE on `conversations`
    # cannot observe the brief window between ADD COLUMN (server_default=0) and
    # the back-fill UPDATE. The lock auto-releases at transaction commit. SQLite
    # has no equivalent statement; the unit-test path uses Base.metadata.create_all
    # and never runs this migration, so this is Postgres-only.
    if bind.dialect.name == "postgresql":
        op.execute("LOCK TABLE conversations IN ACCESS EXCLUSIVE MODE")

    op.add_column(
        "conversations",
        sa.Column("next_ordinal", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE conversations c
        SET next_ordinal = COALESCE((
            SELECT MAX(m.ordinal) + 1
            FROM messages m
            WHERE m.conversation_id = c.id
        ), 0)
        """
    )
    op.alter_column("conversations", "next_ordinal", server_default=None)


def downgrade() -> None:
    op.drop_column("conversations", "next_ordinal")
