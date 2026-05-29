"""add recurrence template tags

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b890
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "task_recurrence_template_tag",
        sa.Column(
            "template_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор шаблона повторяющейся задачи",
        ),
        sa.Column("tag_id", sa.Uuid(), nullable=False, comment="Идентификатор тега"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tag.tag_id"],
            name=op.f("fk_task_recurrence_template_tag_tag_id_tag"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["task_recurrence_template.template_id"],
            name=op.f("fk_task_recurrence_template_tag_template_id_task_recurrence_template"),
        ),
        sa.PrimaryKeyConstraint(
            "template_id",
            "tag_id",
            name=op.f("pk_task_recurrence_template_tag"),
        ),
    )
    op.create_index(
        op.f("ix_task_recurrence_template_tag_tag_id_template_id"),
        "task_recurrence_template_tag",
        ["tag_id", "template_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_task_recurrence_template_tag_tag_id_template_id"),
        table_name="task_recurrence_template_tag",
        if_exists=True,
    )
    op.drop_table("task_recurrence_template_tag", if_exists=True)
