"""add due at and scheduled task

Revision ID: 4b18c2df5a0e
Revises: 19ef4af9c3b1
Create Date: 2026-05-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b18c2df5a0e"
down_revision: Union[str, Sequence[str], None] = "19ef4af9c3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "task",
        sa.Column("due_at", sa.TIMESTAMP(), nullable=True, comment="Дедлайн задачи"),
    )
    op.execute("UPDATE task SET due_at = ends_at")
    op.alter_column("task", "due_at", nullable=False)

    op.create_table(
        "scheduled_task",
        sa.Column("task_id", sa.Uuid(), nullable=False, comment="Идентификатор задачи"),
        sa.Column(
            "starts_at",
            sa.TIMESTAMP(),
            nullable=False,
            comment="Дата/время начала задачи в расписании",
        ),
        sa.Column(
            "ends_at",
            sa.TIMESTAMP(),
            nullable=False,
            comment="Дата/время окончания задачи в расписании",
        ),
        sa.CheckConstraint(
            "ends_at >= starts_at",
            name=op.f("ck_scheduled_task_correct_interval"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.task_id"],
            name=op.f("fk_scheduled_task_task_id_task"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_scheduled_task")),
    )
    op.execute("""
        INSERT INTO scheduled_task(task_id, starts_at, ends_at)
        SELECT task_id, starts_at, ends_at
        FROM task
    """)

    op.drop_constraint(op.f("ck_task_correct_deadline"), "task", type_="check")
    op.drop_column("task", "ends_at")
    op.drop_column("task", "starts_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "task",
        sa.Column(
            "starts_at",
            sa.TIMESTAMP(),
            nullable=True,
            comment="Дата/время начала задачи",
        ),
    )
    op.add_column(
        "task",
        sa.Column(
            "ends_at",
            sa.TIMESTAMP(),
            nullable=True,
            comment="Дата/время окончания задачи",
        ),
    )
    op.execute("""
        UPDATE task
        SET
            starts_at = COALESCE(scheduled_task.starts_at, task.due_at),
            ends_at = COALESCE(scheduled_task.ends_at, task.due_at)
        FROM scheduled_task
        WHERE scheduled_task.task_id = task.task_id
    """)
    op.execute("""
        UPDATE task
        SET starts_at = due_at, ends_at = due_at
        WHERE starts_at IS NULL OR ends_at IS NULL
    """)
    op.alter_column("task", "starts_at", nullable=False)
    op.alter_column("task", "ends_at", nullable=False)
    op.create_check_constraint(
        op.f("ck_task_correct_deadline"),
        "task",
        "ends_at >= starts_at",
    )

    op.drop_table("scheduled_task", if_exists=True)
    op.drop_column("task", "due_at")
