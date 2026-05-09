"""add task priority

Revision ID: b6a1d3e4f902
Revises: a3f4c8b2d901
Create Date: 2026-05-09 00:02:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6a1d3e4f902"
down_revision: Union[str, Sequence[str], None] = "a3f4c8b2d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


task_priority = sa.Enum("low", "normal", "high", "urgent", name="taskpriority")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TYPE IF EXISTS taskpriority")
    task_priority.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "task",
        sa.Column(
            "priority",
            task_priority,
            nullable=False,
            server_default="normal",
            comment="Приоритет задачи",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("task", "priority")
    task_priority.drop(op.get_bind(), checkfirst=True)
