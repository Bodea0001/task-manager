from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime

from domain.value_objects.tasks import FreeTime, Schedule, ScheduleAvailability
from presentation.schemas.tasks import ScheduleSchema, TaskResponse


class FreeTimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    windows: tuple[ScheduleSchema, ...] = Field(min_length=1)

    def to_domain(self) -> tuple[Schedule, ...]:
        return tuple(window.to_domain() for window in self.windows)


class ScheduleAvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: ScheduleSchema

    def to_domain(self) -> Schedule:
        return self.window.to_domain()


class NearestFreeScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_minutes: int = Field(ge=1, le=24 * 60)
    excluded_windows: tuple[ScheduleSchema, ...] = ()
    search_from: NaiveDatetime | None = None

    def duration(self) -> timedelta:
        return timedelta(minutes=self.duration_minutes)

    def excluded_schedules(self) -> tuple[Schedule, ...]:
        return tuple(window.to_domain() for window in self.excluded_windows)


class FreeTimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    free_time: tuple[ScheduleSchema, ...]

    @classmethod
    def from_domain(cls, windows: list[FreeTime]) -> "FreeTimeResponse":
        return cls(
            free_time=tuple(
                ScheduleSchema(starts_at=window.starts_at, ends_at=window.ends_at)
                for window in windows
            )
        )


class ScheduleAvailabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    can_add_task: bool
    blocking_tasks: tuple[TaskResponse, ...]

    @classmethod
    def from_domain(
        cls,
        availability: ScheduleAvailability,
    ) -> "ScheduleAvailabilityResponse":
        return cls(
            can_add_task=availability.can_add_task,
            blocking_tasks=tuple(
                TaskResponse.from_domain(task) for task in availability.blocking_tasks
            ),
        )


class NearestFreeScheduleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule: ScheduleSchema

    @classmethod
    def from_domain(cls, schedule: Schedule) -> "NearestFreeScheduleResponse":
        return cls(schedule=ScheduleSchema.from_domain(schedule))
