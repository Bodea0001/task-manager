from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP, Uuid

from models.base import Base
from models.dependencies import created_at
from domain.value_objects.agent_usage import AgentRunUsageStatus

if TYPE_CHECKING:
    from models.users import User


class UserAgentRunUsage(Base):
    __tablename__ = "user_agent_run_usage"

    run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[AgentRunUsageStatus] = mapped_column(
        Enum(
            AgentRunUsageStatus,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            create_constraint=False,
            length=16,
        ),
        nullable=False,
    )
    reservation_expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[created_at]

    user: Mapped["User"] = relationship("User", back_populates="agent_run_usage")

    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="valid_status",
        ),
        Index("ix_user_agent_run_usage_user_id", "user_id"),
    )
