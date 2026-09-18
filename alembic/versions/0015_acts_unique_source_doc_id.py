"""acts.unique_source_doc_id

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-04

Акт опознаётся только по ``source_doc_id``: ``source`` — описательное поле
(акваер: local-docx / s3-docx / pravo), а не часть ключа идентичности.
Смена акваера при переиндексации меняла ``source`` и, будучи частью
``uq_acts_source_doc = (source, source_doc_id)``, приводила к тому, что
upsert вставлял вторую строку акта вместо обновления существующей —
дубликат акта со всеми статьями и чанками.

Сначала удаляем дубликаты, порождённые сменой акваера (оставляем самую
свежую загрузку по ``ingested_at``; ``articles``/``chunks`` удаляются по
``ON DELETE CASCADE``), затем переставляем уникальный констрейнт на
``source_doc_id`` в одиночку.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Дубликаты, порождённые сменой акваера: у одного source_doc_id несколько
    # строк с разным source. Оставляем самую свежую загрузку; articles и chunks
    # удаляются по ON DELETE CASCADE.
    op.execute(
        """
        DELETE FROM acts a
        USING acts b
        WHERE a.source_doc_id = b.source_doc_id
          AND (a.ingested_at, a.id) < (b.ingested_at, b.id)
        """
    )
    op.drop_constraint("uq_acts_source_doc", "acts", type_="unique")
    op.create_unique_constraint("uq_acts_source_doc_id", "acts", ["source_doc_id"])


def downgrade() -> None:
    # Удалённые в upgrade() дубликаты не восстанавливаются — это осознанное
    # решение (см. докстринг миграции), downgrade лишь возвращает форму
    # констрейнта.
    op.drop_constraint("uq_acts_source_doc_id", "acts", type_="unique")
    op.create_unique_constraint("uq_acts_source_doc", "acts", ["source", "source_doc_id"])
