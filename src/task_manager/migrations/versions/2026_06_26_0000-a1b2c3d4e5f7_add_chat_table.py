"""add chat table

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chat",
        sa.Column(
            "chat_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "creator_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор создателя чата",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
            comment="Признак активного чата пользователя",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Дата и время создания",
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["user.user_id"],
            name=op.f("fk_chat_creator_id_user"),
        ),
        sa.PrimaryKeyConstraint("chat_id", name=op.f("pk_chat")),
    )
    op.create_index(op.f("ix_chat_creator_id"), "chat", ["creator_id"], unique=False)
    op.create_index(
        op.f("ix_chat_active_creator_id_unique"),
        "chat",
        ["creator_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )
    op.execute("""
        CREATE FUNCTION deactivate_other_active_chats()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.is_active IS TRUE THEN
                UPDATE chat
                SET is_active = FALSE
                WHERE
                    creator_id = NEW.creator_id
                    AND chat_id != NEW.chat_id
                    AND is_active IS TRUE;
            END IF;

            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_chat_deactivate_other_active_chats
        BEFORE INSERT OR UPDATE OF is_active
        ON chat
        FOR EACH ROW
        WHEN (NEW.is_active IS TRUE)
        EXECUTE FUNCTION deactivate_other_active_chats();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_chat_deactivate_other_active_chats ON chat")
    op.execute("DROP FUNCTION IF EXISTS deactivate_other_active_chats()")
    op.drop_index(op.f("ix_chat_active_creator_id_unique"), table_name="chat", if_exists=True)
    op.drop_index(op.f("ix_chat_creator_id"), table_name="chat", if_exists=True)
    op.drop_table("chat", if_exists=True)
