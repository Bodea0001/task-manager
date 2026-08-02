"""mark previously modified recurrence instances

Revision ID: e5f6a7b8c921
Revises: d4e5f6a7b910
Create Date: 2026-08-02 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "e5f6a7b8c921"
down_revision: str | Sequence[str] | None = "d4e5f6a7b910"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve recurrence instances previously changed through task use cases."""
    op.execute("""
        UPDATE task_recurrence_instance AS instance
        SET is_customized = true
        FROM task
        WHERE
            task.task_id = instance.task_id
            AND instance.deleted_at IS NULL
            AND instance.is_customized = false
            AND EXISTS (
                SELECT 1
                FROM audit_event AS event
                WHERE
                    event.entity_type = 'task'
                    AND event.entity_id = instance.task_id
                    AND event.actor_user_id = task.creator_id
                    AND event.occurred_at >= instance.created_at
                    AND event.event_type IN (
                        'task.updated',
                        'task.schedule_deleted',
                        'task.occurrence_updated',
                        'task.occurrence_skipped'
                    )
            )
    """)


def downgrade() -> None:
    """Keep repaired customization state because its prior value is not recoverable."""
