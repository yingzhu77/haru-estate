"""Persist successful input mutations and their retry responses atomically."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "mutation_receipts",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )
    op.create_index("ix_runs_created_at", "runs", ["created_at"])


def downgrade() -> None:
    raise RuntimeError("Restore a backup instead of discarding retry receipts.")
