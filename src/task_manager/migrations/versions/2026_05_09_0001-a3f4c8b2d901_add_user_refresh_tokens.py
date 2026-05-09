"""add user refresh tokens

Revision ID: a3f4c8b2d901
Revises: 9b2d7c8f1a4e
Create Date: 2026-05-09 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3f4c8b2d901"
down_revision: Union[str, Sequence[str], None] = "9b2d7c8f1a4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_refresh_token",
        sa.Column(
            "token_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор пользователя",
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 хеш refresh-токена",
        ),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Дата/время истечения refresh-токена",
        ),
        sa.Column(
            "revoked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Дата/время отзыва refresh-токена",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата и время создания",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name=op.f("ck_user_refresh_token_valid_token_hash_length"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.user_id"],
            name=op.f("fk_user_refresh_token_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_id", name=op.f("pk_user_refresh_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_refresh_token_token_hash")),
    )
    op.create_index(
        op.f("ix_user_refresh_token_user_id"),
        "user_refresh_token",
        ["user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_user_refresh_token_user_id"),
        table_name="user_refresh_token",
        if_exists=True,
    )
    op.drop_table("user_refresh_token", if_exists=True)
