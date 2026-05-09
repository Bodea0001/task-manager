"""add audit event log

Revision ID: e8f1a2b3c904
Revises: c9d2e5f6a703
Create Date: 2026-05-09 00:04:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e8f1a2b3c904"
down_revision: Union[str, Sequence[str], None] = "c9d2e5f6a703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_event",
        sa.Column(
            "event_id",
            sa.Uuid(),
            server_default=sa.text("uuidv7()"),
            nullable=False,
            comment="Уникальный идентификатор",
        ),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор пользователя, выполнившего действие",
        ),
        sa.Column("entity_type", sa.String(length=50), nullable=False, comment="Тип сущности"),
        sa.Column(
            "entity_id",
            sa.Uuid(),
            nullable=False,
            comment="Идентификатор измененной сущности",
        ),
        sa.Column("event_type", sa.String(length=100), nullable=False, comment="Тип события"),
        sa.Column(
            "data",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="Безопасные данные события",
        ),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.NOW(),
            nullable=False,
            comment="Дата и время события",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["user.user_id"], name=op.f("fk_audit_event_actor_user_id_user")
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_audit_event")),
    )
    op.create_index(op.f("ix_audit_event_actor_user_id"), "audit_event", ["actor_user_id"])
    op.create_index(
        op.f("ix_audit_event_entity"), "audit_event", ["entity_type", "entity_id", "occurred_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_audit_event_entity"), table_name="audit_event", if_exists=True)
    op.drop_index(op.f("ix_audit_event_actor_user_id"), table_name="audit_event", if_exists=True)
    op.drop_table("audit_event", if_exists=True)
