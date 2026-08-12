"""P2 document_blocks persistence for structured page content."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007_p2_doc_blocks"
down_revision: str | Sequence[str] | None = "006_p2_doc_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_blocks",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_pages.id"),
            nullable=False,
        ),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("bbox_x0", sa.Float(), nullable=True),
        sa.Column("bbox_y0", sa.Float(), nullable=True),
        sa.Column("bbox_x1", sa.Float(), nullable=True),
        sa.Column("bbox_y1", sa.Float(), nullable=True),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "page_id",
            "block_index",
            name="uq_document_blocks_page_block_index",
        ),
    )
    op.create_index(
        "ix_document_blocks_page_id",
        "document_blocks",
        ["page_id"],
    )
    op.create_index(
        "ix_document_blocks_block_type",
        "document_blocks",
        ["block_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_blocks_block_type", table_name="document_blocks")
    op.drop_index("ix_document_blocks_page_id", table_name="document_blocks")
    op.drop_table("document_blocks")
