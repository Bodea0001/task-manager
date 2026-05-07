"""add task model

Revision ID: 29cc06cd0b87
Revises: 88de27b944b0
Create Date: 2026-05-04 23:15:28.999802

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "29cc06cd0b87"
down_revision: Union[str, Sequence[str], None] = "88de27b944b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "task",
        sa.Column(
            "task_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column("title", sa.String(length=250), nullable=False, comment="Заголовок задачи"),
        sa.Column("description", sa.Text(), nullable=True, comment="Подробное описание задачи"),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "cancelled", name="taskstatus"),
            nullable=False,
            server_default="active",
            comment="Статус задачи",
        ),
        sa.Column("starts_at", sa.TIMESTAMP(), nullable=False, comment="Дата/время начала задачи"),
        sa.Column("ends_at", sa.TIMESTAMP(), nullable=False, comment="Дата/время окончания задачи"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата и время создания",
        ),
        sa.Column(
            "completed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время окончания задачи",
        ),
        sa.CheckConstraint("ends_at >= starts_at", name=op.f("ck_task_correct_deadline")),
        sa.CheckConstraint("length(description) > 0", name=op.f("ck_task_non_empty_description")),
        sa.CheckConstraint("length(title) > 0", name=op.f("ck_task_non_empty_title")),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_task")),
    )
    op.execute("""
        CREATE FUNCTION set_completed_timestamp_for_task()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status = 'completed' THEN
                NEW.completed_at = COALESCE(NEW.completed_at, NOW());
            ELSE
                NEW.completed_at = NULL;
            END IF;

            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_task_set_completed_at
        BEFORE INSERT OR UPDATE OF status ON task
        FOR EACH ROW
        EXECUTE FUNCTION set_completed_timestamp_for_task();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_task_set_completed_at ON task")
    op.execute("DROP FUNCTION IF EXISTS set_completed_timestamp_for_task")
    op.drop_table("task")
    op.execute("DROP TYPE IF EXISTS taskstatus")
