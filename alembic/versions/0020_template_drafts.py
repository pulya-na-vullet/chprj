"""template_drafts + messages.template_draft/template_doc

E20 (T-0135): staged-черновики заполнения шаблонов (агент-owned, один на
беседу — инвариант stage→render) и payload'ы карточек шаблонного флоу на
сообщениях (переживают перезагрузку истории, паттерн review-карточки).
Только аддитивно: новая таблица + nullable-колонки.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_drafts",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("template_slug", sa.String(), nullable=False),
        sa.Column("template_title", sa.String(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="template_drafts_conversation_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id", name="template_drafts_pkey"),
    )
    op.add_column("messages", sa.Column("template_draft", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("template_doc", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "template_doc")
    op.drop_column("messages", "template_draft")
    op.drop_table("template_drafts")
