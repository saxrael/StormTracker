"""add_image_hash_and_breakdown_signature

Revision ID: c1f9e2d3b4a5
Revises: b859e41209df
Create Date: 2026-08-19 06:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f9e2d3b4a5"
down_revision: str | None = "b859e41209df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metrics",
        sa.Column("image_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_metrics_image_hash"),
        "metrics",
        ["image_hash"],
        unique=False,
    )
    op.add_column(
        "metrics",
        sa.Column("breakdown_signature", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_metrics_breakdown_signature"),
        "metrics",
        ["breakdown_signature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_metrics_breakdown_signature"),
        table_name="metrics",
    )
    op.drop_column("metrics", "breakdown_signature")
    op.drop_index(
        op.f("ix_metrics_image_hash"),
        table_name="metrics",
    )
    op.drop_column("metrics", "image_hash")
