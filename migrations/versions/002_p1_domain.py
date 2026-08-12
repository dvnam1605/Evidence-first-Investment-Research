"""Alembic domain schema migration."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_p1_domain"
down_revision: str | Sequence[str] | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("industry_code", sa.String(length=32), nullable=True),
        sa.Column("industry_name", sa.String(length=255), nullable=True),
        sa.Column("fiscal_year_end_month", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("ticker", name="uq_companies_ticker"),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_document_id", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("audit_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("object_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "parent_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column("is_correction", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_latest_version", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "processing_status", sa.String(length=32), nullable=False, server_default="PENDING"
        ),
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
    op.create_index("ix_documents_company_id", "documents", ["company_id"])
    op.create_index("ix_documents_published_at", "documents", ["published_at"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_index("ix_documents_source_document", "documents", ["source", "source_document_id"])
    op.create_index("ix_documents_fiscal_period", "documents", ["fiscal_year", "fiscal_quarter"])
    op.create_index("ix_documents_document_type", "documents", ["document_type"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="RUNNING"),
        sa.Column("documents_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_downloaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_ingestion_runs_source", "ingestion_runs", ["source"])
    op.create_index("ix_ingestion_runs_ticker", "ingestion_runs", ["ticker"])


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("documents")
    op.drop_table("companies")
