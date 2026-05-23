from uuid import UUID
from datetime import datetime
from dataclasses import dataclass

from domain.value_objects.tasks import RecurrenceFrequency, Schedule, Task, TaskPriority, TaskStatus


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


@dataclass(frozen=True, slots=True)
class AddTaskRecurrence:
    frequency: RecurrenceFrequency
    schedule: Schedule
    interval: int = 1
    repeat_until: datetime | None = None
    occurrences_limit: int | None = None

    def __post_init__(self) -> None:
        _validate_schedule(self.schedule)
        _validate_recurrence(
            interval=self.interval,
            schedule=self.schedule,
            repeat_until=self.repeat_until,
            occurrences_limit=self.occurrences_limit,
        )


@dataclass(frozen=True, slots=True)
class UpdateTaskRecurrence:
    schedule: Schedule
    repeat_until: datetime | None = None
    occurrences_limit: int | None = None

    def __post_init__(self) -> None:
        _validate_schedule(self.schedule)
        _validate_recurrence_end(
            schedule=self.schedule,
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
    interval: int,
    schedule: Schedule,
    repeat_until: datetime | None,
    occurrences_limit: int | None,
) -> None:
    if interval < 1:
        raise ValueError("recurrence interval must be positive")

    _validate_recurrence_end(
        schedule=schedule,
        repeat_until=repeat_until,
        occurrences_limit=occurrences_limit,
    )


def _validate_recurrence_end(
    *,
    schedule: Schedule,
    repeat_until: datetime | None,
    occurrences_limit: int | None,
) -> None:
    if repeat_until is not None and occurrences_limit is not None:
        raise ValueError("repeat_until and occurrences_limit cannot both be provided")

    if repeat_until is not None and repeat_until < schedule.starts_at:
        raise ValueError("repeat_until cannot be earlier than recurrence start")

    if occurrences_limit is not None and occurrences_limit < 1:
        raise ValueError("occurrences_limit must be positive")
