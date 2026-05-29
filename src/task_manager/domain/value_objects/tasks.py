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


class TaskKind(StrEnum):
    REGULAR = "regular"
    RECURRENCE_CONFLICT = "recurrence_conflict"


class RecurrenceFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RecurrenceCalculationMode(StrEnum):
    SCHEDULED_DATE = "scheduled_date"
    COMPLETION_DATE = "completion_date"


class RecurrenceSkipPolicy(StrEnum):
    ALLOW_OVERDUE = "allow_overdue"
    CREATE_NEXT_INDEPENDENTLY = "create_next_independently"
    CREATE_NEXT_AFTER_COMPLETION = "create_next_after_completion"
    MOVE_TO_NEXT_DATE = "move_to_next_date"


class RecurrenceEndMode(StrEnum):
    NEVER = "never"
    UNTIL_DATE = "until_date"
    COUNT = "count"


class RecurrenceOverrideAction(StrEnum):
    RESCHEDULE = "reschedule"
    MODIFY = "modify"
    SKIP = "skip"
    DELETE = "delete"


class RecurrenceBusinessDayPolicy(StrEnum):
    NONE = "none"
    NEXT_BUSINESS_DAY = "next_business_day"
    PREVIOUS_BUSINESS_DAY = "previous_business_day"


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
    kind: TaskKind = TaskKind.REGULAR
    recurrence_id: UUID | None = None


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


@dataclass(frozen=True, slots=True)
class TaskRecurrenceTemplate:
    template_id: UUID
    title: str
    priority: TaskPriority
    created_at: datetime
    description: str | None = None
    tags: list[Tag] = field(default_factory=list)
    rules: tuple["TaskRecurrence", ...] = ()


@dataclass(frozen=True, slots=True)
class TaskRecurrence:
    recurrence_id: UUID
    template_id: UUID
    frequency: RecurrenceFrequency
    interval: int
    schedule: Schedule
    repeat_until: datetime | None = None
    occurrences_limit: int | None = None


@dataclass(frozen=True, slots=True)
class TaskOccurrence:
    recurrence_id: UUID
    task_id: UUID | None
    original_starts_at: datetime
    schedule: Schedule
    is_cancelled: bool = False
