from typing import Self
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, model_validator

from dto.tasks import AddTask, ListTasksFilters, UpdateTaskData
from domain.value_objects.tasks import (
    Schedule,
    Task,
    TaskKind,
    TaskPriority,
    TaskStatus,
)
from presentation.schemas.tags import TagResponse


class ScheduleSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    starts_at: NaiveDatetime
    ends_at: NaiveDatetime

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.ends_at < self.starts_at:
            raise ValueError("ends_at cannot be earlier than starts_at")
        return self

    def to_domain(self) -> Schedule:
        return Schedule(starts_at=self.starts_at, ends_at=self.ends_at)

    @classmethod
    def from_domain(cls, schedule: Schedule) -> "ScheduleSchema":
        return cls(starts_at=schedule.starts_at, ends_at=schedule.ends_at)


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    due_at: NaiveDatetime
    description: str | None = None
    tag_ids: tuple[UUID, ...] = ()
    status: TaskStatus = TaskStatus.ACTIVE
    priority: TaskPriority = TaskPriority.NORMAL
    schedule: ScheduleSchema | None = None

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> AddTask:
        return AddTask(
            title=self.title,
            due_at=self.due_at,
            description=self.description,
            tag_ids=self.tag_ids,
            status=self.status,
            priority=self.priority,
            schedule=self.schedule.to_domain() if self.schedule is not None else None,
        )


class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: NaiveDatetime | None = None
    schedule: ScheduleSchema | None = None

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> UpdateTaskData:
        return UpdateTaskData(
            title=self.title,
            description=self.description,
            status=self.status,
            priority=self.priority,
            due_at=self.due_at,
            schedule=self.schedule.to_domain() if self.schedule is not None else None,
        )


class TaskListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_ids: tuple[UUID, ...] = ()
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    search_text: str | None = None
    due_from: NaiveDatetime | None = None
    due_to: NaiveDatetime | None = None
    starts_from: NaiveDatetime | None = None
    starts_to: NaiveDatetime | None = None
    ends_from: NaiveDatetime | None = None
    ends_to: NaiveDatetime | None = None
    include_recurring: bool = True
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> ListTasksFilters:
        return ListTasksFilters(
            tag_ids=self.tag_ids,
            statuses=self.statuses,
            priorities=self.priorities,
            search_text=self.search_text,
            due_from=self.due_from,
            due_to=self.due_to,
            starts_from=self.starts_from,
            starts_to=self.starts_to,
            ends_from=self.ends_from,
            ends_to=self.ends_to,
            include_recurring=self.include_recurring,
            limit=self.limit,
            offset=self.offset,
        )


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    kind: TaskKind
    due_at: datetime
    created_at: datetime
    completed_at: datetime | None
    schedule: ScheduleSchema | None
    tags: tuple[TagResponse, ...]
    recurrence_id: UUID | None

    @classmethod
    def from_domain(cls, task: Task) -> "TaskResponse":
        return cls(
            task_id=task.task_id,
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            kind=task.kind,
            due_at=task.due_at,
            created_at=task.created_at,
            completed_at=task.completed_at,
            schedule=(ScheduleSchema.from_domain(task.schedule) if task.schedule else None),
            tags=tuple(TagResponse.from_domain(tag) for tag in task.tags),
            recurrence_id=task.recurrence_id,
        )


class TaskListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks: tuple[TaskResponse, ...]
    conflicts: tuple[TaskResponse, ...] = ()

    @classmethod
    def from_domain(
        cls,
        tasks: list[Task],
        conflicts: list[Task] | None = None,
    ) -> "TaskListResponse":
        return cls(
            tasks=tuple(TaskResponse.from_domain(task) for task in tasks),
            conflicts=tuple(TaskResponse.from_domain(task) for task in conflicts or ()),
        )
