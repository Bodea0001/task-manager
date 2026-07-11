from uuid import UUID
from typing import Annotated
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, field_validator
from langchain.tools import ToolRuntime, InjectedToolArg
from pydantic.json_schema import SkipJsonSchema

from agents.schemas.context import AgentContext
from domain.value_objects.tasks import RecurrenceFrequency, Schedule, TaskPriority, TaskStatus


InjectedRuntime = Annotated[ToolRuntime[AgentContext], InjectedToolArg]
HiddenRuntime = SkipJsonSchema[InjectedRuntime]


class AgentToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    runtime: HiddenRuntime = Field(exclude=True)


class TaskIdToolInput(AgentToolInput):
    task_id: UUID = Field(description="Exact task id for this operation.")


class TagIdToolInput(AgentToolInput):
    tag_id: UUID = Field(description="Exact tag id for this operation.")


class TemplateIdToolInput(AgentToolInput):
    template_id: UUID = Field(description="Exact recurrence template id for this operation.")


class RecurrenceIdToolInput(AgentToolInput):
    recurrence_id: UUID = Field(description="Exact recurrence rule id for this operation.")


class PaginationInput(AgentToolInput):
    limit: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of items to return.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of matching items to skip for pagination.",
    )


class GetTaskInput(TaskIdToolInput):
    pass


class ListTasksInput(AgentToolInput):
    tag_ids: tuple[UUID, ...] = Field(
        default=(),
        description="Optional tag ids used to filter the user's tasks.",
    )
    statuses: tuple[TaskStatus, ...] = Field(
        default=(),
        description="Optional task status filters.",
    )
    priorities: tuple[TaskPriority, ...] = Field(
        default=(),
        description="Optional task priority filters.",
    )
    search_text: str | None = Field(
        default=None, description="Optional title text used to search the user's tasks."
    )
    due_from: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive lower bound for task due_at without timezone offset.",
    )
    due_to: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive upper bound for task due_at without timezone offset.",
    )
    starts_from: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive lower bound for schedule starts_at without timezone offset.",
    )
    starts_to: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive upper bound for schedule starts_at without timezone offset.",
    )
    ends_from: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive lower bound for schedule ends_at without timezone offset.",
    )
    ends_to: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive upper bound for schedule ends_at without timezone offset.",
    )
    include_recurring: bool = Field(
        default=True,
        description="Whether recurring task occurrences should be included.",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of tasks to return.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of matching tasks to skip for pagination.",
    )


class CreateTaskInput(AgentToolInput):
    title: str = Field(description="Task title stated by the user.")
    due_at: NaiveDatetime = Field(
        description="Task deadline as an absolute datetime without timezone offset."
    )
    description: str | None = Field(
        default=None,
        description="Optional task details.",
    )
    tag_ids: tuple[UUID, ...] = Field(
        default=(),
        description="Optional tag ids to attach to the task.",
    )
    status: TaskStatus = Field(
        default=TaskStatus.ACTIVE,
        description="Initial task status.",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL,
        description="Task priority inferred from user intent.",
    )
    schedule: Schedule | None = Field(
        default=None,
        description="Optional scheduled execution window without timezone offsets.",
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule | None) -> Schedule | None:
        if schedule is None:
            return schedule

        _validate_datetime_is_naive(schedule.starts_at, "schedule.starts_at")
        _validate_datetime_is_naive(schedule.ends_at, "schedule.ends_at")
        return schedule


class CompleteTaskInput(TaskIdToolInput):
    pass


class ReopenTaskInput(TaskIdToolInput):
    pass


class CancelTaskInput(TaskIdToolInput):
    pass


class UpdateTaskInput(TaskIdToolInput):
    title: str | None = Field(
        default=None,
        description="New task title. Omit or null leaves the title unchanged.",
    )
    description: str | None = Field(
        default=None,
        description="New task details. Omit or null leaves the description unchanged.",
    )
    status: TaskStatus | None = Field(
        default=None,
        description="New task status. Omit or null leaves the status unchanged.",
    )
    priority: TaskPriority | None = Field(
        default=None,
        description="New task priority. Omit or null leaves the priority unchanged.",
    )
    due_at: NaiveDatetime | None = Field(
        default=None,
        description=(
            "New task deadline without timezone offset. Omit or null leaves the "
            "deadline unchanged; null is not a clear/delete operation."
        ),
    )
    schedule: Schedule | None = Field(
        default=None,
        description=(
            "New scheduled execution window without timezone offsets. Omit or null "
            "leaves the schedule unchanged; use delete_task_schedule to remove a "
            "task schedule."
        ),
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule | None) -> Schedule | None:
        return _validate_optional_schedule_is_naive(schedule)


class CountTasksInput(ListTasksInput):
    pass


class GetOverdueTasksInput(PaginationInput):
    pass


class GetTaskHistoryInput(TaskIdToolInput):
    limit: int = Field(default=100, ge=1, le=100, description="Maximum history events to return.")
    offset: int = Field(default=0, ge=0, description="History events to skip.")


class ScheduleWindowInput(AgentToolInput):
    window: Schedule = Field(description="Schedule window without timezone offsets.")

    @field_validator("window")
    @classmethod
    def validate_window_datetimes_are_naive(cls, window: Schedule) -> Schedule:
        return _validate_schedule_is_naive(window)


class GetFreeTimeInput(AgentToolInput):
    windows: tuple[Schedule, ...] = Field(
        description="One or more schedule windows without timezone offsets.",
    )

    @field_validator("windows")
    @classmethod
    def validate_windows_datetimes_are_naive(
        cls, windows: tuple[Schedule, ...]
    ) -> tuple[Schedule, ...]:
        for window in windows:
            _validate_schedule_is_naive(window)
        return windows


class FindNearestFreeScheduleInput(AgentToolInput):
    duration_minutes: int = Field(ge=1, le=24 * 60, description="Desired free slot duration.")
    excluded_windows: tuple[Schedule, ...] = Field(
        default=(),
        description="Already excluded schedule windows without timezone offsets.",
    )
    search_from: NaiveDatetime | None = Field(
        default=None,
        description="Optional search start datetime without timezone offset.",
    )

    @field_validator("excluded_windows")
    @classmethod
    def validate_excluded_windows_datetimes_are_naive(
        cls, windows: tuple[Schedule, ...]
    ) -> tuple[Schedule, ...]:
        for window in windows:
            _validate_schedule_is_naive(window)
        return windows


class DeleteTaskScheduleInput(TaskIdToolInput):
    pass


class UpdateTaskScheduleInput(TaskIdToolInput):
    schedule: Schedule = Field(
        description="New scheduled execution window without timezone offsets."
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule) -> Schedule:
        return _validate_schedule_is_naive(schedule)


class TaskTagInput(TaskIdToolInput):
    tag_id: UUID = Field(description="Exact tag id for this operation.")


class ListTagsInput(PaginationInput):
    pass


class GetTagInput(TagIdToolInput):
    pass


class GetTagHistoryInput(TagIdToolInput):
    limit: int = Field(default=100, ge=1, le=100, description="Maximum history events to return.")
    offset: int = Field(default=0, ge=0, description="History events to skip.")


class CreateTagInput(AgentToolInput):
    name: str = Field(description="Tag name.")


class EnsureTagInput(CreateTagInput):
    pass


class UpdateTagInput(TagIdToolInput):
    name: str = Field(description="New tag name.")


class ListTaskRecurrenceTemplatesInput(AgentToolInput):
    tag_ids: tuple[UUID, ...] = Field(default=(), description="Optional tag id filters.")
    priorities: tuple[TaskPriority, ...] = Field(
        default=(),
        description="Optional priority filters.",
    )
    frequencies: tuple[RecurrenceFrequency, ...] = Field(
        default=(),
        description="Optional recurrence frequency filters.",
    )
    limit: int = Field(default=100, ge=1, le=100, description="Maximum templates to return.")
    offset: int = Field(default=0, ge=0, description="Templates to skip.")


class CountTaskRecurrenceTemplatesInput(ListTaskRecurrenceTemplatesInput):
    pass


class GetTaskRecurrenceTemplateInput(TemplateIdToolInput):
    pass


class GetTaskRecurrenceTemplateHistoryInput(TemplateIdToolInput):
    limit: int = Field(default=100, ge=1, le=100, description="Maximum history events to return.")
    offset: int = Field(default=0, ge=0, description="History events to skip.")


class RecurrenceTemplateTagInput(TemplateIdToolInput):
    tag_id: UUID = Field(description="Exact tag id for this operation.")


class AddTaskRecurrenceData(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    frequency: RecurrenceFrequency = Field(description="Recurrence frequency.")
    schedule: Schedule = Field(description="Recurrence schedule without timezone offsets.")
    interval: int = Field(default=1, ge=1, description="Positive recurrence interval.")
    repeat_until: NaiveDatetime | None = Field(
        default=None,
        description="Optional recurrence end datetime without timezone offset.",
    )
    occurrences_limit: int | None = Field(
        default=None,
        ge=1,
        description="Optional positive occurrence count limit.",
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule) -> Schedule:
        return _validate_schedule_is_naive(schedule)


class AddTaskRecurrenceTemplateInput(AgentToolInput):
    title: str = Field(description="Recurrence template title.")
    rules: tuple[AddTaskRecurrenceData, ...] = Field(description="One or more recurrence rules.")
    description: str | None = Field(default=None, description="Optional template details.")
    tag_ids: tuple[UUID, ...] = Field(default=(), description="Optional tag ids.")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL, description="Template priority.")


class GetTaskRecurrenceRulesInput(TemplateIdToolInput):
    pass


class AddTaskRecurrenceRuleInput(TemplateIdToolInput):
    frequency: RecurrenceFrequency = Field(description="Recurrence frequency.")
    schedule: Schedule = Field(description="Recurrence schedule without timezone offsets.")
    interval: int = Field(default=1, ge=1, description="Positive recurrence interval.")
    repeat_until: NaiveDatetime | None = Field(
        default=None,
        description="Optional recurrence end datetime without timezone offset.",
    )
    occurrences_limit: int | None = Field(
        default=None,
        ge=1,
        description="Optional positive occurrence count limit.",
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule) -> Schedule:
        return _validate_schedule_is_naive(schedule)


class UpdateTaskRecurrenceInput(RecurrenceIdToolInput):
    schedule: Schedule = Field(description="Updated recurrence schedule without timezone offsets.")
    repeat_until: NaiveDatetime | None = Field(
        default=None,
        description="Optional recurrence end datetime without timezone offset.",
    )
    occurrences_limit: int | None = Field(
        default=None,
        ge=1,
        description="Optional positive occurrence count limit.",
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule) -> Schedule:
        return _validate_schedule_is_naive(schedule)


class StopTaskRecurrenceInput(RecurrenceIdToolInput):
    stop_from: NaiveDatetime = Field(description="Datetime to stop recurrence from.")


class GetTaskOccurrencesInput(TemplateIdToolInput):
    window: Schedule = Field(description="Occurrence lookup window without timezone offsets.")

    @field_validator("window")
    @classmethod
    def validate_window_datetimes_are_naive(cls, window: Schedule) -> Schedule:
        return _validate_schedule_is_naive(window)


class GetRecurrenceInstanceByTaskInput(TaskIdToolInput):
    pass


class UpdateTaskOccurrenceInput(RecurrenceIdToolInput):
    original_starts_at: NaiveDatetime = Field(description="Original occurrence start datetime.")
    title: str | None = Field(default=None, description="Optional occurrence title override.")
    description: str | None = Field(default=None, description="Optional details override.")
    status: TaskStatus | None = Field(default=None, description="Optional status override.")
    priority: TaskPriority | None = Field(default=None, description="Optional priority override.")
    due_at: NaiveDatetime | None = Field(
        default=None,
        description="Optional due_at override without timezone offset.",
    )
    schedule: Schedule | None = Field(
        default=None,
        description="Optional schedule override without timezone offsets.",
    )
    is_cancelled: bool = Field(default=False, description="Whether the occurrence is cancelled.")

    @field_validator("schedule")
    @classmethod
    def validate_schedule_datetimes_are_naive(cls, schedule: Schedule | None) -> Schedule | None:
        return _validate_optional_schedule_is_naive(schedule)


class SkipTaskOccurrenceInput(RecurrenceIdToolInput):
    original_starts_at: NaiveDatetime = Field(description="Original occurrence start datetime.")


def _validate_datetime_is_naive(value: datetime, field_name: str) -> None:
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError(f"{field_name} must not include timezone offset")


def _validate_schedule_is_naive(schedule: Schedule) -> Schedule:
    _validate_datetime_is_naive(schedule.starts_at, "schedule.starts_at")
    _validate_datetime_is_naive(schedule.ends_at, "schedule.ends_at")
    return schedule


def _validate_optional_schedule_is_naive(schedule: Schedule | None) -> Schedule | None:
    if schedule is None:
        return None

    return _validate_schedule_is_naive(schedule)
