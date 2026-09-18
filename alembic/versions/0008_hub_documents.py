"""hub_documents + hub_document_attachments

Creates the documents-hub tables owned by neurolegal.documents. Mirrors
the SQLite-portable models. Independent of the neurolegal.agent/neurolegal.rag schemas.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hub_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("parser", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="hub_documents_pkey"),
        sa.UniqueConstraint("owner_id", "content_hash", name="uq_hub_documents_owner_hash"),
    )
    op.create_index("ix_hub_documents_owner_id", "hub_documents", ["owner_id"])
    op.create_table(
        "hub_document_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["hub_documents.id"],
            name="hub_document_attachments_document_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="hub_document_attachments_pkey"),
        sa.UniqueConstraint(
            "document_id", "conversation_id", name="uq_hub_attach_document_conversation"
        ),
    )
    op.create_index(
        "ix_hub_attach_document_id", "hub_document_attachments", ["document_id"]
    )
    op.create_index(
        "ix_hub_attach_conversation_id", "hub_document_attachments", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_hub_attach_conversation_id", table_name="hub_document_attachments")
    op.drop_index("ix_hub_attach_document_id", table_name="hub_document_attachments")
    op.drop_table("hub_document_attachments")
    op.drop_index("ix_hub_documents_owner_id", table_name="hub_documents")
    op.drop_table("hub_documents")
