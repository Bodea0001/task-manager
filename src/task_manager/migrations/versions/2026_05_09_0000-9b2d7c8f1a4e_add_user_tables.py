"""add user tables

Revision ID: 9b2d7c8f1a4e
Revises: 4b18c2df5a0e
Create Date: 2026-05-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b2d7c8f1a4e"
down_revision: Union[str, Sequence[str], None] = "4b18c2df5a0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user",
        sa.Column(
            "user_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "first_name",
            sa.String(length=250),
            nullable=False,
            comment="Имя пользователя",
        ),
        sa.Column(
            "middle_name",
            sa.String(length=250),
            nullable=True,
            comment="Отчество пользователя",
        ),
        sa.Column(
            "last_name",
            sa.String(length=250),
            nullable=False,
            comment="Фамилия пользователя",
        ),
        sa.Column(
            "email",
            sa.String(length=320),
            nullable=False,
            comment="Email пользователя",
        ),
        sa.CheckConstraint(
            "length(first_name) > 0",
            name=op.f("ck_user_non_empty_first_name"),
        ),
        sa.CheckConstraint(
            "length(middle_name) > 0",
            name=op.f("ck_user_non_empty_middle_name"),
        ),
        sa.CheckConstraint(
            "length(last_name) > 0",
            name=op.f("ck_user_non_empty_last_name"),
        ),
        sa.CheckConstraint("length(email) >= 6", name=op.f("ck_user_valid_email_length")),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )

    op.create_table(
        "user_auth",
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор пользователя",
        ),
        sa.Column(
            "hashed_password",
            sa.String(length=255),
            nullable=False,
            comment="Хеш пароля пользователя",
        ),
        sa.CheckConstraint(
            "length(hashed_password) > 0",
            name=op.f("ck_user_auth_non_empty_hashed_password"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.user_id"],
            name=op.f("fk_user_auth_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_auth")),
    )

    op.add_column(
        "task",
        sa.Column(
            "creator_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор создателя задачи",
        ),
    )
    op.create_foreign_key(
        op.f("fk_task_creator_id_user"),
        "task",
        "user",
        ["creator_id"],
        ["user_id"],
    )
    op.create_index(
        op.f("ix_task_creator_id"),
        "task",
        ["creator_id"],
    )

    op.add_column(
        "tag",
        sa.Column(
            "creator_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор создателя тега",
        ),
    )
    op.create_foreign_key(
        op.f("fk_tag_creator_id_user"),
        "tag",
        "user",
        ["creator_id"],
        ["user_id"],
    )
    op.create_index(
        op.f("ix_tag_creator_id"),
        "tag",
        ["creator_id"],
    )
    op.drop_constraint(op.f("uq_tag_name"), "tag", type_="unique")
    op.create_unique_constraint(
        op.f("uq_tag_creator_id_name"),
        "tag",
        ["creator_id", "name"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("uq_tag_creator_id_name"), "tag", type_="unique")
    op.create_unique_constraint(op.f("uq_tag_name"), "tag", ["name"])
    op.drop_index(op.f("ix_tag_creator_id"), table_name="tag", if_exists=True)
    op.drop_constraint(op.f("fk_tag_creator_id_user"), "tag", type_="foreignkey")
    op.drop_column("tag", "creator_id")
    op.drop_index(op.f("ix_task_creator_id"), table_name="task", if_exists=True)
    op.drop_constraint(op.f("fk_task_creator_id_user"), "task", type_="foreignkey")
    op.drop_column("task", "creator_id")
    op.drop_table("user_auth", if_exists=True)
    op.drop_table("user", if_exists=True)
