"""messages.stopped

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-12

Adds ``stopped`` boolean to ``messages``: the assistant answer was cut short
by the user's stop request and is intentionally partial.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("stopped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("messages", "stopped")
