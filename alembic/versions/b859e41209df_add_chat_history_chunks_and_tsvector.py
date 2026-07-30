"""add_chat_history_chunks_and_tsvector

Revision ID: b859e41209df
Revises: a748b9764cce
Create Date: 2026-07-30 13:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b859e41209df"
down_revision: str | None = "a748b9764cce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_memory_facts",
        sa.Column(
            "search_tsvector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', fact_text)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_memory_tsvector",
        "user_memory_facts",
        ["search_tsvector"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "chat_history_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(2048), nullable=True),
        sa.Column(
            "search_tsvector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', chunk_text)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_chunk_tsvector",
        "chat_history_chunks",
        ["search_tsvector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_chunk_tsvector",
        table_name="chat_history_chunks",
        postgresql_using="gin",
    )
    op.drop_table("chat_history_chunks")
    op.drop_index(
        "ix_memory_tsvector",
        table_name="user_memory_facts",
        postgresql_using="gin",
    )
    op.drop_column("user_memory_facts", "search_tsvector")
