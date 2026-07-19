"""add account verification and agent usage

Revision ID: c3d4e5f6a809
Revises: b2c3d4e5f708
Create Date: 2026-07-18 00:01:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a809"
down_revision: str | Sequence[str] | None = "b2c3d4e5f708"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_email_verification",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_email_verification (user_id, verified_at)
            SELECT user_id, CURRENT_TIMESTAMP
            FROM "user"
            """
        )
    )

    op.create_table(
        "user_agent_run_usage",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reservation_expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="ck_user_agent_run_usage_valid_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_user_agent_run_usage_user_id",
        "user_agent_run_usage",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_agent_run_usage_user_id",
        table_name="user_agent_run_usage",
    )
    op.drop_table("user_agent_run_usage")
    op.drop_table("user_email_verification")
