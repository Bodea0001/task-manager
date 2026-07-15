from uuid import UUID
from enum import IntEnum, StrEnum
from datetime import date, datetime, time, timedelta
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


class Weekday(IntEnum):
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


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
    anchor_date: date
    default_time: time
    default_duration: timedelta | None = None
    weekdays: tuple[Weekday, ...] = ()
    month_rule: "RecurrenceMonthRule | None" = None
    repeat_until: date | None = None
    occurrences_limit: int | None = None

    @property
    def due_at(self) -> datetime:
        starts_at = datetime.combine(self.anchor_date, self.default_time)
        return starts_at + (self.default_duration or timedelta(0))

    @property
    def schedule(self) -> Schedule | None:
        if self.default_duration is None:
            return None
        starts_at = datetime.combine(self.anchor_date, self.default_time)
        return Schedule(starts_at=starts_at, ends_at=starts_at + self.default_duration)


@dataclass(frozen=True, slots=True)
class RecurrenceMonthRule:
    month_day: int | None = None
    week_of_month: int | None = None
    weekday: Weekday | None = None
    business_day_policy: RecurrenceBusinessDayPolicy = RecurrenceBusinessDayPolicy.NONE


@dataclass(frozen=True, slots=True)
class TaskOccurrence:
    recurrence_id: UUID
    task_id: UUID | None
    original_starts_at: datetime
    due_at: datetime
    schedule: Schedule | None = None
    is_cancelled: bool = False
