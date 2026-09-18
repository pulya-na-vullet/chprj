"""users.tour_completed_at

Revision ID: 0018
Revises: 0016
Create Date: 2026-08-12

Тур по продукту (T-0132, спека E19 §9): одна аддитивная nullable-колонка —
отметка «тур завершён/пропущен», ставится флагом ``tour_completed`` в
``PATCH /profile``. Откат кода работает поверх новой схемы.

Ревизия намеренно ``0018`` (а не 0017): параллельная ветка сервиса шаблонов
занимает id 0017 — не создаём дубликат id, alembic-merge при слиянии веток
сведёт головы штатно.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("tour_completed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "tour_completed_at")
