from uuid import UUID
from datetime import datetime
from dataclasses import dataclass

from domain.value_objects.tasks import Schedule, TaskStatus


TITLE_MAX_LENGTH = 250


@dataclass(frozen=True, slots=True)
class ListTasksFilters:
    tag_ids: tuple[UUID, ...] = ()
    statuses: tuple[TaskStatus, ...] = ()
    search_text: str | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    starts_from: datetime | None = None
    starts_to: datetime | None = None
    ends_from: datetime | None = None
    ends_to: datetime | None = None
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
class AddTask:
    title: str
    due_at: datetime
    description: str | None = None
    tag_ids: tuple[UUID, ...] = ()
    status: TaskStatus = TaskStatus.ACTIVE
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
                self.schedule,
            )
        ):
            raise ValueError("at least one task field must be provided")

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
