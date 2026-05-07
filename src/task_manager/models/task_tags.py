from uuid import UUID

from sqlalchemy import Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Uuid

from models.base import Base
from models.dependencies import created_at


class TaskTag(Base):
    __tablename__ = "task_tag"

    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.task_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Идентификатор задачи",
    )
    tag_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tag.tag_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Идентификатор тега",
    )
    created_at: Mapped[created_at]

    __table_args__ = (
        Index("ix_task_tag_tag_id_task_id", "tag_id", "task_id"),
    )
