"""users profile columns

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-12

Профиль-онбординг (T-0126, спека E19 §4): только аддитивные nullable-колонки
в ``users`` — профиль полностью пропускаемый, дефолтов нет, откат кода
работает поверх новой схемы. Значения ``usage_kind``/``role``/``tasks``
валидируются контрактом ``PATCH /profile`` (перечисления в
``contracts/auth.py``), БД ограничений на значения не накладывает.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("avatar_preset", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("usage_kind", sa.String(), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(), nullable=True))
    op.add_column("users", sa.Column("tasks", sa.JSON(), nullable=True))
    op.add_column("users", sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarded_at")
    op.drop_column("users", "tasks")
    op.drop_column("users", "role")
    op.drop_column("users", "usage_kind")
    op.drop_column("users", "avatar_preset")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
