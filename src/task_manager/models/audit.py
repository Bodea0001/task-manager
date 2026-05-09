from uuid import UUID
from typing import Any

from sqlalchemy import text, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import String, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from models.base import Base
from models.dependencies import created_at, uuidpk


class AuditEvent(Base):
    __tablename__ = "audit_event"

    event_id: Mapped[uuidpk]
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id"),
        comment="Идентификатор пользователя, выполнившего действие",
    )
    entity_type: Mapped[str] = mapped_column(String(50), comment="Тип измененной сущности")
    entity_id: Mapped[UUID] = mapped_column(Uuid, comment="Идентификатор измененной сущности")
    event_type: Mapped[str] = mapped_column(String(100), comment="Тип события")
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), comment="Безопасные данные события"
    )
    occurred_at: Mapped[created_at]

    __table_args__ = (
        Index("ix_audit_event_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_audit_event_actor_user_id", "actor_user_id"),
    )
