"""add tag model

Revision ID: 6fd7a4c2f7aa
Revises: 29cc06cd0b87
Create Date: 2026-05-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6fd7a4c2f7aa"
down_revision: Union[str, Sequence[str], None] = "29cc06cd0b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tag",
        sa.Column(
            "tag_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column("name", sa.String(length=100), nullable=False, comment="Название тега"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата и время создания",
        ),
        sa.CheckConstraint("length(name) > 0", name=op.f("ck_tag_non_empty_name")),
        sa.PrimaryKeyConstraint("tag_id", name=op.f("pk_tag")),
        sa.UniqueConstraint("name", name=op.f("uq_tag_name")),
    )

    op.create_table(
        "task_tag",
        sa.Column("task_id", sa.Uuid(), nullable=False, comment="Идентификатор задачи"),
        sa.Column("tag_id", sa.Uuid(), nullable=False, comment="Идентификатор тега"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата и время создания",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tag.tag_id"],
            name=op.f("fk_task_tag_tag_id_tag"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.task_id"],
            name=op.f("fk_task_tag_task_id_task"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", "tag_id", name=op.f("pk_task_tag")),
    )
    op.create_index(
        op.f("ix_task_tag_tag_id_task_id"),
        "task_tag",
        ["tag_id", "task_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_task_tag_tag_id_task_id"), table_name="task_tag", if_exists=True)
    op.drop_table("task_tag", if_exists=True)
    op.drop_table("tag", if_exists=True)
