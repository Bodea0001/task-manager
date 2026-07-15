from uuid import UUID
from datetime import date, datetime, time, timedelta
from dataclasses import dataclass

from domain.value_objects.tasks import (
    Weekday,
    Schedule,
    Task,
    TaskPriority,
    TaskStatus,
    RecurrenceFrequency,
    RecurrenceMonthRule,
)


TITLE_MAX_LENGTH = 250


@dataclass(frozen=True, slots=True)
class ListTasksFilters:
    tag_ids: tuple[UUID, ...] = ()
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    search_text: str | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    starts_from: datetime | None = None
    starts_to: datetime | None = None
    ends_from: datetime | None = None
    ends_to: datetime | None = None
    include_recurring: bool = True
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        if self.due_from is not None and self.due_to is not None:
            if self.due_from > self.due_to:
                raise ValueError("due_from cannot be later than due_to")

        if self.starts_from is not None and self.starts_to is not None:
            if self.starts_from > self.starts_to:
                raise ValueError("starts_from cannot be later than starts_to")

        if self.ends_from is not None and self.ends_to is not None:
            if self.ends_from > self.ends_to:
                raise ValueError("ends_from cannot be later than ends_to")

        if self.starts_from is not None and self.ends_to is not None:
            if self.starts_from > self.ends_to:
                raise ValueError("starts_from cannot be later than ends_to")


@dataclass(frozen=True, slots=True)
class TaskList:
    tasks: list[Task]
    conflicts: list[Task]


@dataclass(frozen=True, slots=True)
class ListTaskRecurrenceTemplatesFilters:
    tag_ids: tuple[UUID, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    frequencies: tuple[RecurrenceFrequency, ...] = ()
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class AddTask:
    title: str
    due_at: datetime
    description: str | None = None
    tag_ids: tuple[UUID, ...] = ()
    status: TaskStatus = TaskStatus.ACTIVE
    priority: TaskPriority = TaskPriority.NORMAL
    schedule: Schedule | None = None

    def __post_init__(self) -> None:
        _trim_text_fields(self, "title", "description")

        _validate_title(self.title)
        _validate_description(self.description)
        _validate_schedule(self.schedule)


@dataclass(frozen=True, slots=True)
class UpdateTaskData:
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    schedule: Schedule | None = None

    def __post_init__(self) -> None:
        _trim_text_fields(self, "title", "description")

        if all(
            value is None
            for value in (
                self.due_at,
                self.title,
                self.description,
                self.status,
                self.priority,
                self.schedule,
            )
        ):
            raise ValueError("at least one task field must be provided")

        _validate_title(self.title)
        _validate_description(self.description)
        _validate_schedule(self.schedule)


@dataclass(frozen=True, slots=True)
class AddTaskRecurrenceTemplate:
    title: str
    rules: tuple["AddTaskRecurrence", ...]
    description: str | None = None
    tag_ids: tuple[UUID, ...] = ()
    priority: TaskPriority = TaskPriority.NORMAL

    def __post_init__(self) -> None:
        _trim_text_fields(self, "title", "description")

        if not self.rules:
            raise ValueError("at least one recurrence rule must be provided")

        _validate_title(self.title)
        _validate_description(self.description)


@dataclass(frozen=True, slots=True)
class UpdateTaskRecurrenceTemplate:
    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None

    def __post_init__(self) -> None:
        _trim_text_fields(self, "title", "description")

        if self.title is None and self.description is None and self.priority is None:
            raise ValueError("at least one recurrence template field must be provided")

        _validate_title(self.title)
        _validate_description(self.description)


@dataclass(frozen=True, slots=True, kw_only=True)
class _TaskRecurrenceData:
    frequency: RecurrenceFrequency
    anchor_date: date
    default_time: time
    interval: int = 1
    default_duration: timedelta | None = None
    weekdays: tuple[Weekday, ...] = ()
    month_rule: RecurrenceMonthRule | None = None
    repeat_until: date | None = None
    occurrences_limit: int | None = None

    def __post_init__(self) -> None:
        _validate_recurrence(
            frequency=self.frequency,
            interval=self.interval,
            anchor_date=self.anchor_date,
            default_time=self.default_time,
            default_duration=self.default_duration,
            weekdays=self.weekdays,
            month_rule=self.month_rule,
            repeat_until=self.repeat_until,
            occurrences_limit=self.occurrences_limit,
        )


@dataclass(frozen=True, slots=True)
class AddTaskRecurrence(_TaskRecurrenceData):
    pass


@dataclass(frozen=True, slots=True)
class UpdateTaskRecurrence:
    anchor_date: date
    default_time: time
    default_duration: timedelta | None = None
    repeat_until: date | None = None
    occurrences_limit: int | None = None

    def __post_init__(self) -> None:
        if self.default_time.tzinfo is not None:
            raise ValueError("default_time must not include a timezone offset")
        if self.default_duration is not None and self.default_duration <= timedelta(0):
            raise ValueError("default_duration must be positive")
        _validate_recurrence_end(
            anchor_date=self.anchor_date,
            repeat_until=self.repeat_until,
            occurrences_limit=self.occurrences_limit,
        )


@dataclass(frozen=True, slots=True)
class UpdateTaskOccurrence:
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    schedule: Schedule | None = None
    is_cancelled: bool = False

    def __post_init__(self) -> None:
        if (
            all(
                value is None
                for value in (
                    self.title,
                    self.description,
                    self.status,
                    self.priority,
                    self.due_at,
                    self.schedule,
                )
            )
            and not self.is_cancelled
        ):
            raise ValueError("schedule or is_cancelled must be provided")

        if self.schedule is not None and self.is_cancelled:
            raise ValueError("cancelled occurrence cannot have an override schedule")

        _trim_text_fields(self, "title", "description")
        _validate_title(self.title)
        _validate_description(self.description)
        _validate_schedule(self.schedule)


def _trim_text_fields(instance, *field_names: str) -> None:
    for field_name in field_names:
        value = getattr(instance, field_name)

        if value is not None:
            object.__setattr__(instance, field_name, value.strip())


def _validate_title(title: str | None) -> None:
    if title is None:
        return

    if len(title) == 0:
        raise ValueError("title cannot be empty")

    if len(title) > TITLE_MAX_LENGTH:
        raise ValueError(f"title cannot be longer than {TITLE_MAX_LENGTH} characters")


def _validate_description(description: str | None) -> None:
    if description is None:
        return

    if len(description) == 0:
        raise ValueError("description cannot be empty")


def _validate_schedule(schedule: Schedule | None) -> None:
    if schedule is None:
        return

    if schedule.ends_at < schedule.starts_at:
        raise ValueError("ends_at cannot be earlier than starts_at")


def _validate_recurrence(
    *,
    frequency: RecurrenceFrequency,
    interval: int,
    anchor_date: date,
    default_time: time,
    default_duration: timedelta | None,
    weekdays: tuple[Weekday, ...],
    month_rule: RecurrenceMonthRule | None,
    repeat_until: date | None,
    occurrences_limit: int | None,
) -> None:
    if interval < 1:
        raise ValueError("recurrence interval must be positive")

    if default_time.tzinfo is not None:
        raise ValueError("default_time must not include a timezone offset")

    if default_duration is not None and default_duration <= timedelta(0):
        raise ValueError("default_duration must be positive")

    normalized_weekdays = tuple(dict.fromkeys(weekdays))
    if normalized_weekdays != weekdays:
        raise ValueError("recurrence weekdays must be unique")

    if frequency == RecurrenceFrequency.WEEKLY and not weekdays:
        raise ValueError("weekly recurrence requires at least one weekday")
    if frequency != RecurrenceFrequency.WEEKLY and weekdays:
        raise ValueError("weekdays are only supported for weekly recurrence")

    if frequency == RecurrenceFrequency.MONTHLY and month_rule is None:
        raise ValueError("monthly recurrence requires a month rule")
    if frequency != RecurrenceFrequency.MONTHLY and month_rule is not None:
        raise ValueError("month_rule is only supported for monthly recurrence")
    if month_rule is not None:
        _validate_month_rule(month_rule)

    _validate_recurrence_end(
        anchor_date=anchor_date,
        repeat_until=repeat_until,
        occurrences_limit=occurrences_limit,
    )


def _validate_recurrence_end(
    *,
    anchor_date: date,
    repeat_until: date | None,
    occurrences_limit: int | None,
) -> None:
    if repeat_until is not None and occurrences_limit is not None:
        raise ValueError("repeat_until and occurrences_limit cannot both be provided")

    if repeat_until is not None and repeat_until < anchor_date:
        raise ValueError("repeat_until cannot be earlier than recurrence start")

    if occurrences_limit is not None and occurrences_limit < 1:
        raise ValueError("occurrences_limit must be positive")


def _validate_month_rule(rule: RecurrenceMonthRule) -> None:
    uses_month_day = rule.month_day is not None
    uses_ordinal_weekday = rule.week_of_month is not None or rule.weekday is not None

    if uses_month_day == uses_ordinal_weekday:
        raise ValueError("month rule must use either month_day or an ordinal weekday")
    if uses_month_day and rule.month_day is not None and not 1 <= rule.month_day <= 31:
        raise ValueError("month_day must be between 1 and 31")
    if uses_ordinal_weekday:
        if rule.week_of_month is None or rule.weekday is None:
            raise ValueError("ordinal month rule requires week_of_month and weekday")
        if rule.week_of_month not in {-1, 1, 2, 3, 4, 5}:
            raise ValueError("week_of_month must be -1 or between 1 and 5")
