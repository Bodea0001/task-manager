"""require recurrence default time

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make recurrence time required and duration strictly positive."""
    op.execute(
        "UPDATE task_recurrence_series SET default_time = TIME '00:00' WHERE default_time IS NULL"
    )
    op.execute("""
        DELETE FROM scheduled_task AS schedule
        USING task_recurrence_instance AS instance, task
        WHERE
            schedule.task_id = instance.task_id
            AND task.task_id = instance.task_id
            AND instance.series_id IN (
                SELECT series_id
                FROM task_recurrence_series
                WHERE default_duration <= INTERVAL '0 seconds'
            )
            AND instance.deleted_at IS NULL
            AND instance.is_customized = false
            AND task.deleted_at IS NULL
            AND task.status != 'completed'
            AND schedule.starts_at = schedule.ends_at
    """)
    op.execute("""
        UPDATE task_recurrence_series
        SET default_duration = NULL
        WHERE default_duration <= INTERVAL '0 seconds'
    """)
    op.drop_constraint(
        op.f("ck_task_recurrence_series_duration_requires_time"),
        "task_recurrence_series",
        type_="check",
    )
    op.alter_column(
        "task_recurrence_series",
        "default_time",
        existing_type=sa.Time(),
        nullable=False,
        comment="Время дедлайна экземпляра",
    )
    op.create_check_constraint(
        op.f("ck_task_recurrence_series_positive_default_duration"),
        "task_recurrence_series",
        "default_duration IS NULL OR default_duration > INTERVAL '0 seconds'",
    )


def downgrade() -> None:
    """Restore the previous recurrence-time constraint."""
    op.drop_constraint(
        op.f("ck_task_recurrence_series_positive_default_duration"),
        "task_recurrence_series",
        type_="check",
    )
    op.alter_column(
        "task_recurrence_series",
        "default_time",
        existing_type=sa.Time(),
        nullable=True,
        comment="Время экземпляра, если задача запланирована",
    )
    op.create_check_constraint(
        op.f("ck_task_recurrence_series_duration_requires_time"),
        "task_recurrence_series",
        "default_duration IS NULL OR default_time IS NOT NULL",
    )
