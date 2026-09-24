"""Persist read-only agent work independently of browser sessions."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_agent_tasks_run_id", "agent_tasks", ["run_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])


def downgrade() -> None:
    raise RuntimeError("Restore a backup instead of discarding persisted agent tasks.")
