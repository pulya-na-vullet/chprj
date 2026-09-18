"""template_drafts.document_id / document_filename

T-0143: идемпотентность render_template. `document_id` пишется сразу после
успешного upload — до attach, поэтому оборванная попытка (upload прошёл,
attach упал) переиспользует загруженный документ вместо второй загрузки, а
повторный render уже отрендеренного черновика возвращает готовый документ.
Только аддитивно: две nullable-колонки.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("template_drafts", sa.Column("document_id", sa.String(length=36), nullable=True))
    op.add_column("template_drafts", sa.Column("document_filename", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("template_drafts", "document_filename")
    op.drop_column("template_drafts", "document_id")
