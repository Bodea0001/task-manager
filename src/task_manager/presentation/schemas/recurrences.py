from typing import Self
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, model_validator

from dto.tasks import (
    AddTaskRecurrence,
    AddTaskRecurrenceTemplate,
    ListTaskRecurrenceTemplatesFilters,
    UpdateTaskOccurrence,
    UpdateTaskRecurrence,
)
from domain.value_objects.tasks import (
    RecurrenceFrequency,
    Schedule,
    TaskOccurrence,
    TaskPriority,
    TaskRecurrence,
    TaskRecurrenceTemplate,
    TaskStatus,
)
from presentation.schemas.tags import TagResponse
from presentation.schemas.tasks import ScheduleSchema


class CreateRecurrenceRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frequency: RecurrenceFrequency
    schedule: ScheduleSchema
    interval: int = Field(default=1, ge=1)
    repeat_until: NaiveDatetime | None = None
    occurrences_limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> AddTaskRecurrence:
        return AddTaskRecurrence(
            frequency=self.frequency,
            schedule=self.schedule.to_domain(),
            interval=self.interval,
            repeat_until=self.repeat_until,
            occurrences_limit=self.occurrences_limit,
        )


class CreateRecurrenceTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    rules: tuple[CreateRecurrenceRuleRequest, ...]
    description: str | None = None
    tag_ids: tuple[UUID, ...] = ()
    priority: TaskPriority = TaskPriority.NORMAL

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> AddTaskRecurrenceTemplate:
        return AddTaskRecurrenceTemplate(
            title=self.title,
            rules=tuple(rule.to_dto() for rule in self.rules),
            description=self.description,
            tag_ids=self.tag_ids,
            priority=self.priority,
        )


class UpdateRecurrenceRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: ScheduleSchema
    repeat_until: NaiveDatetime | None = None
    occurrences_limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> UpdateTaskRecurrence:
        return UpdateTaskRecurrence(
            schedule=self.schedule.to_domain(),
            repeat_until=self.repeat_until,
            occurrences_limit=self.occurrences_limit,
        )


class StopRecurrenceRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_from: NaiveDatetime


class RecurrenceTemplateListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_ids: tuple[UUID, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    frequencies: tuple[RecurrenceFrequency, ...] = ()
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    def to_dto(self) -> ListTaskRecurrenceTemplatesFilters:
        return ListTaskRecurrenceTemplatesFilters(
            tag_ids=self.tag_ids,
            priorities=self.priorities,
            frequencies=self.frequencies,
            limit=self.limit,
            offset=self.offset,
        )


class OccurrenceWindowQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: NaiveDatetime
    ends_at: NaiveDatetime

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        self.to_domain()
        return self

    def to_domain(self) -> Schedule:
        return ScheduleSchema(starts_at=self.starts_at, ends_at=self.ends_at).to_domain()


class UpdateOccurrenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: NaiveDatetime | None = None
    schedule: ScheduleSchema | None = None
    is_cancelled: bool = False

    @model_validator(mode="after")
    def validate_dto(self) -> Self:
        self.to_dto()
        return self

    def to_dto(self) -> UpdateTaskOccurrence:
        return UpdateTaskOccurrence(
            title=self.title,
            description=self.description,
            status=self.status,
            priority=self.priority,
            due_at=self.due_at,
            schedule=self.schedule.to_domain() if self.schedule is not None else None,
            is_cancelled=self.is_cancelled,
        )


class RecurrenceRuleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recurrence_id: UUID
    template_id: UUID
    frequency: RecurrenceFrequency
    interval: int
    schedule: ScheduleSchema
    repeat_until: datetime | None
    occurrences_limit: int | None

    @classmethod
    def from_domain(cls, rule: TaskRecurrence) -> "RecurrenceRuleResponse":
        return cls(
            recurrence_id=rule.recurrence_id,
            template_id=rule.template_id,
            frequency=rule.frequency,
            interval=rule.interval,
            schedule=ScheduleSchema.from_domain(rule.schedule),
            repeat_until=rule.repeat_until,
            occurrences_limit=rule.occurrences_limit,
        )


class RecurrenceRuleListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rules: tuple[RecurrenceRuleResponse, ...]

    @classmethod
    def from_domain(cls, rules: list[TaskRecurrence]) -> "RecurrenceRuleListResponse":
        return cls(rules=tuple(RecurrenceRuleResponse.from_domain(rule) for rule in rules))


class RecurrenceTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: UUID
    title: str
    description: str | None
    priority: TaskPriority
    created_at: datetime
    tags: tuple[TagResponse, ...]
    rules: tuple[RecurrenceRuleResponse, ...]

    @classmethod
    def from_domain(cls, template: TaskRecurrenceTemplate) -> "RecurrenceTemplateResponse":
        return cls(
            template_id=template.template_id,
            title=template.title,
            description=template.description,
            priority=template.priority,
            created_at=template.created_at,
            tags=tuple(TagResponse.from_domain(tag) for tag in template.tags),
            rules=tuple(RecurrenceRuleResponse.from_domain(rule) for rule in template.rules),
        )


class RecurrenceTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    templates: tuple[RecurrenceTemplateResponse, ...]

    @classmethod
    def from_domain(
        cls,
        templates: list[TaskRecurrenceTemplate],
    ) -> "RecurrenceTemplateListResponse":
        return cls(
            templates=tuple(
                RecurrenceTemplateResponse.from_domain(template) for template in templates
            )
        )


class OccurrenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recurrence_id: UUID
    task_id: UUID | None
    original_starts_at: datetime
    schedule: ScheduleSchema
    is_cancelled: bool

    @classmethod
    def from_domain(cls, occurrence: TaskOccurrence) -> "OccurrenceResponse":
        return cls(
            recurrence_id=occurrence.recurrence_id,
            task_id=occurrence.task_id,
            original_starts_at=occurrence.original_starts_at,
            schedule=ScheduleSchema.from_domain(occurrence.schedule),
            is_cancelled=occurrence.is_cancelled,
        )


class OccurrenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurrences: tuple[OccurrenceResponse, ...]

    @classmethod
    def from_domain(cls, occurrences: list[TaskOccurrence]) -> "OccurrenceListResponse":
        return cls(occurrences=tuple(OccurrenceResponse.from_domain(item) for item in occurrences))


class OptionalOccurrenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurrence: OccurrenceResponse | None

    @classmethod
    def from_domain(cls, occurrence: TaskOccurrence | None) -> "OptionalOccurrenceResponse":
        return cls(occurrence=OccurrenceResponse.from_domain(occurrence) if occurrence else None)
