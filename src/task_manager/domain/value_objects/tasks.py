from uuid import UUID
from enum import StrEnum
from datetime import datetime
from dataclasses import field, dataclass

from domain.value_objects.tags import Tag


class TaskStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass(frozen=True, slots=True)
class Task:
    task_id: UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime
    created_at: datetime
    description: str | None = None
    completed_at: datetime | None = None
    schedule: Schedule | None = None
    tags: list[Tag] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Schedule:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class FreeTime:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class ScheduleAvailability:
    can_add_task: bool
    blocking_tasks: list[Task] = field(default_factory=list)
