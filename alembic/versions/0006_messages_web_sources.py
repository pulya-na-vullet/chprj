"""messages.web_sources

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-13

Adds ``web_sources`` JSON column to ``messages``, mirroring ``citations``.
Stores optional list of web search result objects attached to an assistant
message.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("web_sources", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "web_sources")
