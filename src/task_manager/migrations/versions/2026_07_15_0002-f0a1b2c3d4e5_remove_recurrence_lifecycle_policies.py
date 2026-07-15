"""remove recurrence lifecycle policies

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-15 02:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


calculation_mode = postgresql.ENUM(
    "scheduled_date",
    "completion_date",
    name="recurrencecalculationmode",
    create_type=False,
)
skip_policy = postgresql.ENUM(
    "allow_overdue",
    "create_next_independently",
    "create_next_after_completion",
    "move_to_next_date",
    name="recurrenceskippolicy",
    create_type=False,
)


def upgrade() -> None:
    """Remove lifecycle settings that do not have runtime behavior."""
    op.drop_column("task_recurrence_series", "skip_policy")
    op.drop_column("task_recurrence_series", "calculation_mode")
    skip_policy.drop(op.get_bind(), checkfirst=True)
    calculation_mode.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Restore the former lifecycle settings with their legacy defaults."""
    calculation_mode.create(op.get_bind(), checkfirst=True)
    skip_policy.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "task_recurrence_series",
        sa.Column(
            "calculation_mode",
            calculation_mode,
            nullable=False,
            server_default="scheduled_date",
            comment="От какой даты считать следующий экземпляр",
        ),
    )
    op.add_column(
        "task_recurrence_series",
        sa.Column(
            "skip_policy",
            skip_policy,
            nullable=False,
            server_default="allow_overdue",
            comment="Что делать с серией при пропуске экземпляра",
        ),
    )
    op.alter_column("task_recurrence_series", "calculation_mode", server_default=None)
    op.alter_column("task_recurrence_series", "skip_policy", server_default=None)
