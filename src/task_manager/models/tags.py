from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import String

from models.base import Base
from models.dependencies import created_at, uuidpk

if TYPE_CHECKING:
    from models.tasks import Task


class Tag(Base):
    __tablename__ = "tag"

    tag_id: Mapped[uuidpk]
    name: Mapped[str] = mapped_column(String(100), comment="Название тега")
    created_at: Mapped[created_at]

    tasks: Mapped[list[Task]] = relationship(
        "Task",
        secondary="task_tag",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint("length(name) > 0", "non_empty_name"),
        UniqueConstraint("name"),
    )
