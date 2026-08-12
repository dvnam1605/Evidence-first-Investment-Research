"""P1 split ingestion into publications, artifacts, and raw objects."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_p1_publication_artifacts"
down_revision: str | Sequence[str] | None = "002_p1_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_objects",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
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
        "ix_raw_objects_sha256", "raw_objects", ["sha256"], unique=True
    )

    op.create_table(
        "source_publications",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "source_document_id", sa.String(length=255), nullable=False
        ),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column(
            "scope",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "audit_status",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column(
            "parent_publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_publications.id"),
            nullable=True,
        ),
        sa.Column(
            "is_correction",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_latest_version",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            nullable=False,
            server_default="PENDING",
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
        sa.UniqueConstraint(
            "source", "source_document_id", name="uq_source_publications_natural_key"
        ),
    )
    op.create_index(
        "ix_source_publications_company_id",
        "source_publications",
        ["company_id"],
    )
    op.create_index(
        "ix_source_publications_published_at",
        "source_publications",
        ["published_at"],
    )

    op.create_table(
        "document_artifacts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_publications.id"),
            nullable=False,
        ),
        sa.Column(
            "attachment_reference", sa.Text(), nullable=False
        ),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "raw_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_objects.id"),
            nullable=False,
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
        sa.UniqueConstraint(
            "publication_id",
            "attachment_reference",
            name="uq_document_artifacts_publication_attachment",
        ),
    )
    op.create_index(
        "ix_document_artifacts_publication_id",
        "document_artifacts",
        ["publication_id"],
    )

    # Backfill P1 tables from legacy `documents` rows.
    #
    # This keeps rerun/idempotency semantics stable after the split:
    # - publications natural key: (source, source_document_id)
    # - raw objects natural key: sha256
    # - artifacts natural key: (publication_id, attachment_reference)
    #
    # Note: legacy schema had a single attachment per document; we map the
    # legacy object_path as the attachment_reference to maintain determinism.
    bind = op.get_bind()
    # raw_objects (dedupe by sha256)
    bind.execute(
        sa.text(
            """
            INSERT INTO raw_objects (id, sha256, object_path, mime_type, size_bytes)
            SELECT
                x.id,
                x.sha256,
                x.object_path,
                x.mime_type,
                x.file_size
            FROM (
                SELECT
                    d.id,
                    d.sha256,
                    d.object_path,
                    d.mime_type,
                    d.file_size,
                    ROW_NUMBER() OVER (
                        PARTITION BY d.sha256
                        ORDER BY d.id::text
                    ) AS rn
                FROM documents d
            ) x
            WHERE x.rn = 1
            ON CONFLICT (sha256) DO NOTHING;
            """
        )
    )

    # source_publications (natural key: source + source_document_id)
    bind.execute(
        sa.text(
            """
            INSERT INTO source_publications (
                id,
                company_id,
                source,
                source_document_id,
                document_type,
                title,
                published_at,
                period_start,
                period_end,
                fiscal_year,
                fiscal_quarter,
                scope,
                audit_status,
                language,
                source_reference,
                parent_publication_id,
                is_correction,
                is_latest_version,
                processing_status
            )
            SELECT
                d.id AS id,
                d.company_id AS company_id,
                d.source AS source,
                d.source_document_id AS source_document_id,
                d.document_type AS document_type,
                d.title AS title,
                d.published_at AS published_at,
                d.period_start AS period_start,
                d.period_end AS period_end,
                d.fiscal_year AS fiscal_year,
                d.fiscal_quarter AS fiscal_quarter,
                d.scope AS scope,
                d.audit_status AS audit_status,
                d.language AS language,
                d.source_reference AS source_reference,
                d.parent_document_id AS parent_publication_id,
                d.is_correction AS is_correction,
                d.is_latest_version AS is_latest_version,
                d.processing_status AS processing_status
            FROM documents d
            ON CONFLICT ON CONSTRAINT uq_source_publications_natural_key DO NOTHING;
            """
        )
    )

    # document_artifacts (legacy mapping: object_path -> attachment_reference)
    bind.execute(
        sa.text(
            """
            INSERT INTO document_artifacts (
                id,
                publication_id,
                attachment_reference,
                filename,
                mime_type,
                file_size,
                raw_object_id
            )
            SELECT
                d.id AS id,
                d.id AS publication_id,
                d.object_path AS attachment_reference,
                d.filename AS filename,
                d.mime_type AS mime_type,
                d.file_size AS file_size,
                r.id AS raw_object_id
            FROM documents d
            JOIN raw_objects r
              ON r.sha256 = d.sha256
            ON CONFLICT ON CONSTRAINT uq_document_artifacts_publication_attachment DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_document_artifacts_publication_id", table_name="document_artifacts")
    op.drop_table("document_artifacts")
    op.drop_index("ix_source_publications_published_at", table_name="source_publications")
    op.drop_index("ix_source_publications_company_id", table_name="source_publications")
    op.drop_table("source_publications")
    op.drop_index("ix_raw_objects_sha256", table_name="raw_objects")
    op.drop_table("raw_objects")

