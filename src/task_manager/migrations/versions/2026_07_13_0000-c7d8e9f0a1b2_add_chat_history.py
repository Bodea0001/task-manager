"""add chat history

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f7
Create Date: 2026-07-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat",
        sa.Column(
            "title",
            sa.String(length=250),
            server_default="New chat",
            nullable=False,
            comment="Название чата",
        ),
    )

    chat_message_role = postgresql.ENUM(
        "user",
        "assistant",
        name="chatmessagerole",
        create_type=False,
    )
    chat_message_role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "chat_message",
        sa.Column(
            "message_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "chat_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор чата",
        ),
        sa.Column(
            "role",
            chat_message_role,
            nullable=False,
            comment="Роль автора сообщения",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="Текст сообщения",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Дата и время создания",
        ),
        sa.CheckConstraint("length(content) > 0", name=op.f("ck_chat_message_non_empty_content")),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chat.chat_id"],
            name=op.f("fk_chat_message_chat_id_chat"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_chat_message")),
    )
    op.create_index(
        "ix_chat_message_chat_id_created_at",
        "chat_message",
        ["chat_id", "created_at", "message_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_chat_message_chat_id_created_at",
        table_name="chat_message",
        if_exists=True,
    )
    op.drop_table("chat_message", if_exists=True)
    postgresql.ENUM(name="chatmessagerole").drop(op.get_bind(), checkfirst=True)
    op.drop_column("chat", "title")
