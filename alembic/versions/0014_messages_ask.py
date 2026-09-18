"""messages.ask

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-18

Adds nullable ``ask`` JSON column to ``messages``: the persisted shape of a
paused-for-input turn (e.g. review role clarification), replayed via
``GET /conversations/{id}/messages`` (T-0046). NULL = not a paused turn.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("ask", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "ask")
