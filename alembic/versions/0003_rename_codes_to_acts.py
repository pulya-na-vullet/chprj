"""rename codes→acts, add kind

The `kind` column is added NOT NULL with a temporary `server_default="codex"`,
which is dropped immediately after. This pattern is safe on an empty table.
This migration assumes no production data exists; if rows were already present
they would silently be classified as codex by the default. Validate before
running on a live database.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop derived indexes first (they reference column names we'll rename)
    op.execute("DROP INDEX IF EXISTS ix_chunks_code_id")
    op.execute("DROP INDEX IF EXISTS ix_structure_nodes_code_id")

    # Drop UNIQUE constraints we'll recreate after rename
    op.execute("ALTER TABLE codes DROP CONSTRAINT IF EXISTS uq_codes_source_doc")
    op.execute("ALTER TABLE articles DROP CONSTRAINT IF EXISTS uq_articles_code_number")

    # Rename tables
    op.rename_table("codes", "acts")
    # PostgreSQL does not rename the PK constraint when the table is renamed.
    op.execute("ALTER TABLE acts RENAME CONSTRAINT codes_pkey TO acts_pkey")

    # Rename FK columns in dependents
    op.alter_column("structure_nodes", "code_id", new_column_name="act_id")
    op.alter_column("articles", "code_id", new_column_name="act_id")
    op.alter_column("chunks", "code_id", new_column_name="act_id")

    # PostgreSQL does not rename FK constraint names when the column is renamed.
    op.execute(
        "ALTER TABLE structure_nodes "
        "RENAME CONSTRAINT structure_nodes_code_id_fkey TO structure_nodes_act_id_fkey"
    )
    op.execute(
        "ALTER TABLE articles "
        "RENAME CONSTRAINT articles_code_id_fkey TO articles_act_id_fkey"
    )
    op.execute(
        "ALTER TABLE chunks "
        "RENAME CONSTRAINT chunks_code_id_fkey TO chunks_act_id_fkey"
    )

    # kind is added NOT NULL via temporary server_default; see module docstring
    op.add_column(
        "acts",
        sa.Column(
            "kind",
            sa.String(),
            nullable=False,
            server_default="codex",
        ),
    )
    op.alter_column("acts", "kind", server_default=None)
    op.execute(
        "ALTER TABLE acts ADD CONSTRAINT ck_acts_kind "
        "CHECK (kind IN ('codex','federal_law'))"
    )

    # Recreate UNIQUE constraints
    op.create_unique_constraint("uq_acts_source_doc", "acts", ["source", "source_doc_id"])
    op.create_unique_constraint("uq_articles_act_number", "articles", ["act_id", "number"])

    # Recreate indexes with new names
    op.create_index("ix_structure_nodes_act_id", "structure_nodes", ["act_id"])
    op.create_index("ix_chunks_act_id", "chunks", ["act_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_act_id", table_name="chunks")
    op.drop_index("ix_structure_nodes_act_id", table_name="structure_nodes")
    op.drop_constraint("uq_articles_act_number", "articles", type_="unique")
    op.drop_constraint("uq_acts_source_doc", "acts", type_="unique")
    op.execute("ALTER TABLE acts DROP CONSTRAINT IF EXISTS ck_acts_kind")
    op.drop_column("acts", "kind")
    op.execute(
        "ALTER TABLE chunks "
        "RENAME CONSTRAINT chunks_act_id_fkey TO chunks_code_id_fkey"
    )
    op.execute(
        "ALTER TABLE articles "
        "RENAME CONSTRAINT articles_act_id_fkey TO articles_code_id_fkey"
    )
    op.execute(
        "ALTER TABLE structure_nodes "
        "RENAME CONSTRAINT structure_nodes_act_id_fkey TO structure_nodes_code_id_fkey"
    )
    op.alter_column("chunks", "act_id", new_column_name="code_id")
    op.alter_column("articles", "act_id", new_column_name="code_id")
    op.alter_column("structure_nodes", "act_id", new_column_name="code_id")
    op.execute("ALTER TABLE acts RENAME CONSTRAINT acts_pkey TO codes_pkey")
    op.rename_table("acts", "codes")
    op.create_unique_constraint("uq_codes_source_doc", "codes", ["source", "source_doc_id"])
    op.create_unique_constraint("uq_articles_code_number", "articles", ["code_id", "number"])
    op.create_index("ix_structure_nodes_code_id", "structure_nodes", ["code_id"])
    op.create_index("ix_chunks_code_id", "chunks", ["code_id"])
