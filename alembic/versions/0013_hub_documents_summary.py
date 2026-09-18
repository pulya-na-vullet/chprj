"""hub_documents.summary

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-12

Adds nullable ``summary`` to ``hub_documents``: the one-line LLM «Суть»
shown in the Files register (T-0017). NULL = not computed yet.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hub_documents", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("hub_documents", "summary")
