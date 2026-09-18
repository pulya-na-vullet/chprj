"""search_vector and pgvector indexes"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('russian', "text")) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute("CREATE INDEX chunks_search_vector_gin ON chunks USING gin (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_search_vector_gin")
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS search_vector")
