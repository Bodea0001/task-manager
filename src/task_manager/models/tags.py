from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import String, Uuid

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

    creator: Mapped["User"] = relationship("User", back_populates="created_tags")
    tasks: Mapped[list[Task]] = relationship(
        "Task",
        secondary="task_tag",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint("length(name) > 0", "non_empty_name"),
        UniqueConstraint("creator_id", "name"),
    )
