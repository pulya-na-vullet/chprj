"""tpl_templates

Creates the templates-service table owned by neurolegal.templates. Mirrors the
SQLite-portable model. Independent of the agent/rag/documents schemas.

Жила на ветке как 0017 поверх 0015; при подготовке мержа (2026-08-13)
перенумерована в 0019 поверх 0018_users_tour — E19 успела влиться в main
первой и заняла номера 0016/0018. Таблицы веток не связаны, перевешивание
безопасно.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tpl_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="tpl_templates_pkey"),
        sa.UniqueConstraint("slug", name="uq_tpl_templates_slug"),
    )


def downgrade() -> None:
    op.drop_table("tpl_templates")
