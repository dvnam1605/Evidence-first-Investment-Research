"""Add date-only source update fields to source_publications."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_p1_srcupd_prec"
down_revision: str | Sequence[str] | None = "003_p1_publication_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Allow discovery timestamps to be date-only without fabricating time-of-day.
    op.alter_column(
        "source_publications",
        "published_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )

    op.add_column(
        "source_publications",
        sa.Column("source_updated_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "source_publications",
        sa.Column("published_at_precision", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_publications", "published_at_precision")
    op.drop_column("source_publications", "source_updated_date")

    op.alter_column(
        "source_publications",
        "published_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

