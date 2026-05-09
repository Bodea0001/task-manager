from uuid import UUID
from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Index, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import String, Text, Uuid, TIMESTAMP, Enum
from sqlalchemy.dialects.postgresql import TSVECTOR

from models.base import Base
from models.dependencies import created_at, uuidpk
from domain.value_objects.tasks import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from models.tags import Tag
    from models.users import User


class Task(Base):
    __tablename__ = "task"

    task_id: Mapped[uuidpk]
    title: Mapped[str] = mapped_column(String(250), comment="Заголовок задачи")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Подробное описание задачи"
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=lambda enum: [member.value for member in enum]),
        server_default=TaskStatus.ACTIVE,
        comment="Статус задачи",
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, values_callable=lambda enum: [member.value for member in enum]),
        server_default=TaskPriority.NORMAL,
        comment="Приоритет задачи",
    )
    due_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), comment="Дедлайн задачи")
    creator_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.user_id"), comment="Идентификатор создателя задачи"
    )
    created_at: Mapped[created_at]
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время окончания задачи"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время мягкого удаления задачи"
    )

    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="task_tag", viewonly=True, order_by="Tag.name"
    )
    creator: Mapped["User"] = relationship("User", back_populates="created_tasks")
    schedule: Mapped["ScheduledTask | None"] = relationship(
        "ScheduledTask",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )

    __table_args__ = (
        CheckConstraint("length(title) > 0", "non_empty_title"),
        CheckConstraint("length(description) > 0", "non_empty_description"),
    )


class ScheduledTask(Base):
    __tablename__ = "scheduled_task"

    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.task_id"),
        primary_key=True,
        comment="Идентификатор задачи",
    )
    starts_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), comment="Дата/время начала задачи в расписании"
    )
    ends_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), comment="Дата/время окончания задачи в расписании"
    )

    task: Mapped[Task] = relationship("Task", back_populates="schedule")

    __table_args__ = (
        CheckConstraint(
            "ends_at >= starts_at",
            "correct_interval",
        ),
    )


class TaskStore(Base):
    __tablename__ = "task_store"

    task_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("task.task_id"),
        primary_key=True,
        comment="Идентификатор задачи",
    )
    tsv_content: Mapped[str] = mapped_column(TSVECTOR, comment="Поисковый вектор задачи")

    __table_args__ = (Index("ix_task_store_tsv_content", "tsv_content", postgresql_using="gin"),)
