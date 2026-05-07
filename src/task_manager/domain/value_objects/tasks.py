from uuid import UUID
from enum import StrEnum
from datetime import datetime
from dataclasses import field, dataclass

from domain.value_objects.tags import Tag


class TaskStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Task:
    task_id: UUID
    title: str
    status: TaskStatus
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    description: str | None = None
    completed_at: datetime | None = None
    tags: list[Tag] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict):
        data["status"] = TaskStatus(data["status"])
        return cls(**data)
