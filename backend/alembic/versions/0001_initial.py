"""Initial immutable revision and run storage."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("known_on", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "version"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), unique=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("snapshots", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
    )
    op.create_index("ix_runs_status", "runs", ["status"])


def downgrade() -> None:
    raise RuntimeError("Demo migration downgrade is intentionally unsupported; restore a backup.")
