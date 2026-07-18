"""add active recurrence tail index

Revision ID: b2c3d4e5f708
Revises: a1b2c3d4e6f7
Create Date: 2026-07-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f708"
down_revision: str | Sequence[str] | None = "a1b2c3d4e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_task_recurrence_instance_active_series_planned_start",
        "task_recurrence_instance",
        ["series_id", "planned_starts_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_recurrence_instance_active_series_planned_start",
        table_name="task_recurrence_instance",
    )
