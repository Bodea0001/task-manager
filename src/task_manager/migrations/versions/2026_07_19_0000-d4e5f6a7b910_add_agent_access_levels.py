"""add agent access levels

Revision ID: d4e5f6a7b910
Revises: c3d4e5f6a809
Create Date: 2026-07-19 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e5f6a7b910"
down_revision: str | Sequence[str] | None = "c3d4e5f6a809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


agent_access_level = postgresql.ENUM(
    "limited",
    "unmetered",
    name="agent_access_level",
    create_type=False,
)


def upgrade() -> None:
    agent_access_level.create(op.get_bind(), checkfirst=False)
    op.create_table(
        "user_agent_access",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "access_level",
            agent_access_level,
            server_default=sa.text("'limited'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_agent_access (user_id, access_level)
            SELECT user_id, 'limited'
            FROM "user"
            """
        )
    )


def downgrade() -> None:
    op.drop_table("user_agent_access")
    agent_access_level.drop(op.get_bind(), checkfirst=False)
