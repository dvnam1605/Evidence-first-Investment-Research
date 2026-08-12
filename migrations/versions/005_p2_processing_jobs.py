"""P2 document processing job tracking."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_p2_proc_jobs"
down_revision: str | Sequence[str] | None = "004_p1_srcupd_prec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_processing_jobs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_artifacts.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("parser", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_document_processing_jobs_artifact_id",
        "document_processing_jobs",
        ["artifact_id"],
    )
    op.create_index(
        "ix_document_processing_jobs_status",
        "document_processing_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_processing_jobs_status",
        table_name="document_processing_jobs",
    )
    op.drop_index(
        "ix_document_processing_jobs_artifact_id",
        table_name="document_processing_jobs",
    )
    op.drop_table("document_processing_jobs")
