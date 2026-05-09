from uuid import UUID
from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Index, CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import String, Uuid, TIMESTAMP

from models.base import Base
from models.dependencies import created_at, uuidpk

if TYPE_CHECKING:
    from models.tasks import Task
    from models.users import User


class Tag(Base):
    __tablename__ = "tag"

    tag_id: Mapped[uuidpk]
    name: Mapped[str] = mapped_column(String(100), comment="Название тега")
    creator_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id"),
        comment="Идентификатор создателя тега",
    )
    created_at: Mapped[created_at]
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления тега"
    )

    creator: Mapped["User"] = relationship("User", back_populates="created_tags")
    tasks: Mapped[list[Task]] = relationship(
        "Task",
        secondary="task_tag",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint("length(name) > 0", "non_empty_name"),
        Index(
            "ix_tag_active_creator_id_name",
            "creator_id",
            "name",
            unique=True,
            postgresql_where=deleted_at.is_(None),
        ),
    )
