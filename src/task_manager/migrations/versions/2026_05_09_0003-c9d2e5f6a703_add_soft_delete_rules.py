"""add soft delete rules

Revision ID: c9d2e5f6a703
Revises: b6a1d3e4f902
Create Date: 2026-05-09 00:03:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d2e5f6a703"
down_revision: Union[str, Sequence[str], None] = "b6a1d3e4f902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASCADE_FOREIGN_KEYS = (
    (
        "fk_user_auth_user_id_user",
        "user_auth",
        "user",
        ["user_id"],
        ["user_id"],
    ),
    (
        "fk_user_refresh_token_user_id_user",
        "user_refresh_token",
        "user",
        ["user_id"],
        ["user_id"],
    ),
    (
        "fk_task_tag_task_id_task",
        "task_tag",
        "task",
        ["task_id"],
        ["task_id"],
    ),
    (
        "fk_task_tag_tag_id_tag",
        "task_tag",
        "tag",
        ["tag_id"],
        ["tag_id"],
    ),
    (
        "fk_scheduled_task_task_id_task",
        "scheduled_task",
        "task",
        ["task_id"],
        ["task_id"],
    ),
    (
        "fk_task_store_task_id_task",
        "task_store",
        "task",
        ["task_id"],
        ["task_id"],
    ),
)


def upgrade() -> None:
    """Upgrade schema."""
    _replace_foreign_keys(ondelete=None)

    op.add_column(
        "task",
        sa.Column(
            "deleted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время мягкого удаления задачи",
        ),
    )
    op.add_column(
        "tag",
        sa.Column(
            "deleted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время мягкого удаления тега",
        ),
    )

    op.drop_constraint(op.f("uq_tag_creator_id_name"), "tag", type_="unique")
    op.create_index(
        op.f("ix_tag_active_creator_id_name"),
        "tag",
        ["creator_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.execute("""
        CREATE RULE soft_delete_task AS
        ON DELETE TO task
        DO INSTEAD
            UPDATE task
            SET deleted_at = NOW()
            WHERE
                task.task_id = OLD.task_id
                AND task.deleted_at IS NULL
    """)
    op.execute("""
        CREATE RULE soft_delete_tag AS
        ON DELETE TO tag
        DO INSTEAD
            UPDATE tag
            SET deleted_at = NOW()
            WHERE
                tag.tag_id = OLD.tag_id
                AND tag.deleted_at IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP RULE IF EXISTS soft_delete_tag ON tag")
    op.execute("DROP RULE IF EXISTS soft_delete_task ON task")

    op.drop_index(op.f("ix_tag_active_creator_id_name"), table_name="tag", if_exists=True)
    op.create_unique_constraint(op.f("uq_tag_creator_id_name"), "tag", ["creator_id", "name"])

    op.drop_column("tag", "deleted_at")
    op.drop_column("task", "deleted_at")

    _replace_foreign_keys(ondelete="CASCADE")


def _replace_foreign_keys(ondelete: str | None) -> None:
    for name, source_table, referent_table, local_cols, remote_cols in CASCADE_FOREIGN_KEYS:
        op.drop_constraint(op.f(name), source_table, type_="foreignkey")
        op.create_foreign_key(
            op.f(name),
            source_table,
            referent_table,
            local_cols,
            remote_cols,
            ondelete=ondelete,
        )
