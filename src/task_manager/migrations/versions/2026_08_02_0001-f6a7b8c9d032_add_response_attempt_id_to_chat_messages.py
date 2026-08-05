"""add response attempt id to chat messages

Revision ID: f6a7b8c9d032
Revises: e5f6a7b8c921
Create Date: 2026-08-02 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d032"
down_revision: str | Sequence[str] | None = "e5f6a7b8c921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Correlate unresolved user messages with their current response attempt."""
    op.add_column(
        "chat_message",
        sa.Column(
            "response_attempt_id",
            sa.Uuid(),
            nullable=True,
            comment="Идентификатор текущей попытки ответа на сообщение",
        ),
    )
    op.create_index(
        "ix_chat_message_response_attempt_id_unique",
        "chat_message",
        ["response_attempt_id"],
        unique=True,
        postgresql_where=sa.text("response_attempt_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove response-attempt correlation from chat messages."""
    op.drop_index(
        "ix_chat_message_response_attempt_id_unique",
        table_name="chat_message",
    )
    op.drop_column("chat_message", "response_attempt_id")
