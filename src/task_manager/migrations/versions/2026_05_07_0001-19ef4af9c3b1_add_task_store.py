"""add task store

Revision ID: 19ef4af9c3b1
Revises: 6fd7a4c2f7aa
Create Date: 2026-05-07 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "19ef4af9c3b1"
down_revision: Union[str, Sequence[str], None] = "6fd7a4c2f7aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "task_store",
        sa.Column(
            "task_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор задачи",
        ),
        sa.Column(
            "tsv_content",
            postgresql.TSVECTOR(),
            nullable=False,
            comment="Поисковый вектор задачи",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.task_id"],
            name=op.f("fk_task_store_task_id_task"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_task_store")),
    )
    op.create_index(
        op.f("ix_task_store_tsv_content"),
        "task_store",
        ["tsv_content"],
        postgresql_using="gin",
    )
    op.execute("""
        CREATE FUNCTION sync_task_store_tsv_content()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO task_store(task_id, tsv_content)
            VALUES (
                NEW.task_id,
                setweight(to_tsvector('russian', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', COALESCE(NEW.description, '')), 'B')
            )
            ON CONFLICT (task_id) DO UPDATE
            SET tsv_content = EXCLUDED.tsv_content;

            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_task_sync_store_tsv_content
        AFTER INSERT OR UPDATE OF title, description ON task
        FOR EACH ROW
        EXECUTE FUNCTION sync_task_store_tsv_content();
    """)
    op.execute("""
        INSERT INTO task_store(task_id, tsv_content)
        SELECT
            task_id,
            setweight(to_tsvector('russian', COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('russian', COALESCE(description, '')), 'B')
        FROM task
        ON CONFLICT (task_id) DO UPDATE
        SET tsv_content = EXCLUDED.tsv_content;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_task_sync_store_tsv_content ON task")
    op.execute("DROP FUNCTION IF EXISTS sync_task_store_tsv_content")
    op.drop_index(op.f("ix_task_store_tsv_content"), table_name="task_store", if_exists=True)
    op.drop_table("task_store", if_exists=True)
