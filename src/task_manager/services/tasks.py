from uuid import UUID
from typing import Any
from datetime import datetime, timedelta
from collections.abc import Iterable

import exceptions as app_exc
from dto.tasks import (
    AddTask,
    TaskList,
    UpdateTaskData,
    ListTasksFilters,
    AddTaskRecurrence,
    UpdateTaskRecurrence,
    UpdateTaskOccurrence,
    AddTaskRecurrenceTemplate,
    ListTaskRecurrenceTemplatesFilters,
)
from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.value_objects.tasks import (
    Task,
    FreeTime,
    Schedule,
    TaskStatus,
    TaskRecurrence,
    TaskOccurrence,
    ScheduleAvailability,
    TaskRecurrenceTemplate,
)
from domain.value_objects.audit import AuditEvent, AuditEntityType, AuditEventType


class TaskService:
    """Application service with task operations intended for agent tools/use cases."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    # Tasks

    async def get_task(self, user_id: UUID, task_id: UUID) -> Task:
        async with self.uow(read_only=True) as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            return await uow.task.get_task(user_id, task_id)

    async def get_tasks(self, user_id: UUID, filters: ListTasksFilters | None = None) -> TaskList:
        if filters is None:
            filters = ListTasksFilters()

        async with self.uow(read_only=True) as uow:
            return await uow.task.get_tasks(user_id, filters)

    async def count_tasks(self, user_id: UUID, filters: ListTasksFilters | None = None) -> int:
        if filters is None:
            filters = ListTasksFilters()

        async with self.uow(read_only=True) as uow:
            return await uow.task.count_tasks(user_id, filters)

    async def get_active_tasks(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        result = await self.get_tasks(
            user_id, ListTasksFilters(statuses=(TaskStatus.ACTIVE,), limit=limit, offset=offset)
        )
        return result.tasks

    async def get_completed_tasks(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        result = await self.get_tasks(
            user_id, ListTasksFilters(statuses=(TaskStatus.COMPLETED,), limit=limit, offset=offset)
        )
        return result.tasks

    async def get_overdue_tasks(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_overdue_tasks(user_id, limit, offset)

    async def get_task_history(
        self, user_id: UUID, task_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[AuditEvent]:
        async with self.uow(read_only=True) as uow:
            await self._check_if_task_belongs_to_user(uow, user_id, task_id)
            return await uow.audit.get_events(
                entity_type=AuditEntityType.TASK,
                entity_id=task_id,
                limit=limit,
                offset=offset,
            )

    async def create_task(self, user_id: UUID, data: AddTask) -> Task:
        async with self.uow() as uow:
            task = await uow.task.add_task(user_id, data)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=task.task_id,
                event_type=AuditEventType.TASK_CREATED,
                data={
                    "tag_ids": [str(tag_id) for tag_id in data.tag_ids],
                    "has_schedule": data.schedule is not None,
                },
            )
            return task

    async def update_task(self, user_id: UUID, task_id: UUID, data: UpdateTaskData) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            task = await uow.task.update_task(user_id, task_id, data)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=task_id,
                event_type=AuditEventType.TASK_UPDATED,
                data={"changed_fields": self._changed_task_fields(data)},
            )
            return task

    async def complete_task(self, user_id: UUID, task_id: UUID) -> Task:
        return await self.update_task(user_id, task_id, UpdateTaskData(status=TaskStatus.COMPLETED))

    async def reopen_task(self, user_id: UUID, task_id: UUID) -> Task:
        return await self.update_task(user_id, task_id, UpdateTaskData(status=TaskStatus.ACTIVE))

    async def cancel_task(self, user_id: UUID, task_id: UUID) -> Task:
        return await self.update_task(user_id, task_id, UpdateTaskData(status=TaskStatus.CANCELLED))

    async def delete_task(self, user_id: UUID, task_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await uow.task.delete_task(user_id, task_id)
            await self._record_task_event(
                uow, user_id=user_id, task_id=task_id, event_type=AuditEventType.TASK_DELETED
            )

    # Schedule

    async def get_free_time(self, user_id: UUID, windows: Iterable[Schedule]) -> list[FreeTime]:
        schedule_windows = self._prepare_schedule_windows(windows)

        async with self.uow(read_only=True) as uow:
            return await uow.task.get_free_time(user_id, schedule_windows)

    async def check_schedule_availability(
        self, user_id: UUID, window: Schedule
    ) -> ScheduleAvailability:
        async with self.uow(read_only=True) as uow:
            blocking_tasks = await uow.task.get_schedule_blocking_tasks(user_id, window)
            return ScheduleAvailability(
                can_add_task=not blocking_tasks,
                blocking_tasks=blocking_tasks,
            )

    async def find_nearest_free_schedule(
        self,
        user_id: UUID,
        duration: timedelta,
        excluded_windows: tuple[Schedule, ...] = (),
        search_from: datetime | None = None,
    ) -> Schedule:
        if duration <= timedelta(0):
            raise ValueError("duration must be positive")

        if search_from is None:
            search_from = datetime.now()

        self._validate_schedule_windows(excluded_windows)

        async with self.uow(read_only=True) as uow:
            return await uow.task.find_nearest_free_schedule(
                user_id=user_id,
                duration=duration,
                excluded_windows=excluded_windows,
                search_from=search_from,
            )

    async def delete_schedule_from_task(self, user_id: UUID, task_id: UUID) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await uow.task.delete_schedule_from_task(user_id, task_id)
            task = await uow.task.get_task(user_id, task_id)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=task_id,
                event_type=AuditEventType.TASK_SCHEDULE_DELETED,
            )
            return task

    # Task tags

    async def add_tag_to_task(self, user_id: UUID, task_id: UUID, tag_id: UUID) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await self._check_if_tag_exists(uow, user_id, tag_id)
            await uow.task.add_tag_to_task(user_id, task_id, tag_id)
            task = await uow.task.get_task(user_id, task_id)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=task_id,
                event_type=AuditEventType.TASK_TAG_ADDED,
                data={"tag_id": str(tag_id)},
            )
            return task

    async def delete_tag_from_task(self, user_id: UUID, task_id: UUID, tag_id: UUID) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await self._check_if_tag_exists(uow, user_id, tag_id)
            await uow.task.delete_tag_from_task(user_id, task_id, tag_id)
            task = await uow.task.get_task(user_id, task_id)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=task_id,
                event_type=AuditEventType.TASK_TAG_REMOVED,
                data={"tag_id": str(tag_id)},
            )
            return task

    # Recurrence templates

    async def get_task_recurrence_template(
        self, user_id: UUID, template_id: UUID
    ) -> TaskRecurrenceTemplate:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_task_recurrence_template(user_id, template_id)

    async def get_task_recurrence_templates(
        self, user_id: UUID, filters: ListTaskRecurrenceTemplatesFilters | None = None
    ) -> list[TaskRecurrenceTemplate]:
        if filters is None:
            filters = ListTaskRecurrenceTemplatesFilters()

        async with self.uow(read_only=True) as uow:
            return await uow.task.get_task_recurrence_templates(user_id, filters)

    async def count_task_recurrence_templates(
        self, user_id: UUID, filters: ListTaskRecurrenceTemplatesFilters | None = None
    ) -> int:
        if filters is None:
            filters = ListTaskRecurrenceTemplatesFilters()

        async with self.uow(read_only=True) as uow:
            return await uow.task.count_task_recurrence_templates(user_id, filters)

    async def add_task_recurrence_template(
        self, user_id: UUID, data: AddTaskRecurrenceTemplate
    ) -> TaskRecurrenceTemplate:
        async with self.uow() as uow:
            template = await uow.task.add_task_recurrence_template(user_id, data)
            await self._record_task_events(
                uow,
                [
                    {
                        "user_id": user_id,
                        "task_id": template.template_id,
                        "event_type": AuditEventType.TASK_RECURRENCE_ADDED,
                        "data": {
                            "recurrence_id": str(recurrence.recurrence_id),
                            "frequency": recurrence.frequency.value,
                            "interval": recurrence.interval,
                        },
                    }
                    for recurrence in template.rules
                ],
            )
            return template

    # Recurrence rules

    async def get_task_recurrence_rules(
        self, user_id: UUID, template_id: UUID
    ) -> list[TaskRecurrence]:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_task_recurrence_rules(user_id, template_id)

    async def add_task_recurrence_rule(
        self, user_id: UUID, template_id: UUID, data: AddTaskRecurrence
    ) -> TaskRecurrence:
        async with self.uow() as uow:
            recurrence = await uow.task.add_task_recurrence_rule(user_id, template_id, data)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=template_id,
                event_type=AuditEventType.TASK_RECURRENCE_ADDED,
                data={
                    "recurrence_id": str(recurrence.recurrence_id),
                    "frequency": recurrence.frequency.value,
                    "interval": recurrence.interval,
                },
            )
            return recurrence

    async def update_task_recurrence(
        self, user_id: UUID, recurrence_id: UUID, data: UpdateTaskRecurrence
    ) -> TaskRecurrence:
        async with self.uow() as uow:
            recurrence = await uow.task.update_task_recurrence(user_id, recurrence_id, data)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=recurrence.template_id,
                event_type=AuditEventType.TASK_RECURRENCE_UPDATED,
                data={
                    "recurrence_id": str(recurrence_id),
                    "frequency": recurrence.frequency.value,
                    "interval": recurrence.interval,
                },
            )
            return recurrence

    async def stop_task_recurrence(
        self, user_id: UUID, recurrence_id: UUID, stop_from: datetime
    ) -> TaskRecurrence:
        async with self.uow() as uow:
            recurrence = await uow.task.stop_task_recurrence(user_id, recurrence_id, stop_from)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=recurrence.template_id,
                event_type=AuditEventType.TASK_RECURRENCE_STOPPED,
                data={"recurrence_id": str(recurrence_id), "stop_from": stop_from.isoformat()},
            )
            return recurrence

    async def recalculate_future_recurrence_instances(
        self, user_id: UUID, recurrence_id: UUID, from_datetime: datetime
    ) -> None:
        async with self.uow() as uow:
            template_id = await uow.task.get_recurrence_template_id(user_id, recurrence_id)
            await uow.task.recalculate_future_recurrence_instances(
                user_id=user_id,
                recurrence_id=recurrence_id,
                from_datetime=from_datetime,
            )
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=template_id,
                event_type=AuditEventType.TASK_RECURRENCE_RECALCULATED,
                data={"recurrence_id": str(recurrence_id), "from": from_datetime.isoformat()},
            )

    async def delete_task_recurrence(self, user_id: UUID, recurrence_id: UUID) -> None:
        async with self.uow() as uow:
            template_id = await uow.task.get_recurrence_template_id(user_id, recurrence_id)
            await uow.task.delete_task_recurrence(user_id, recurrence_id)
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=template_id,
                event_type=AuditEventType.TASK_RECURRENCE_DELETED,
                data={"recurrence_id": str(recurrence_id)},
            )

    # Recurrence materialization and occurrences

    async def get_task_occurrences(
        self, user_id: UUID, template_id: UUID, window: Schedule
    ) -> list[TaskOccurrence]:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_task_occurrences(user_id, template_id, window)

    async def get_recurrence_instance_by_task_id(
        self, user_id: UUID, task_id: UUID
    ) -> TaskOccurrence | None:
        async with self.uow(read_only=True) as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            return await uow.task.get_recurrence_instance_by_task_id(user_id, task_id)

    async def materialize_recurrence_instances(
        self, user_id: UUID, windows: Iterable[Schedule]
    ) -> None:
        schedule_windows = self._prepare_schedule_windows(windows)
        async with self.uow() as uow:
            await uow.task.materialize_recurrence_instances(user_id, schedule_windows)

    async def materialize_recurrence_instances_for_all_owners(self, window: Schedule) -> int:
        schedule_windows = self._prepare_schedule_windows((window,))
        async with self.uow(read_only=True) as uow:
            user_ids = await uow.task.get_recurrence_owner_ids_requiring_materialization(
                schedule_windows[0]
            )

        for user_id in user_ids:
            await self.materialize_recurrence_instances(user_id, schedule_windows)

        return len(user_ids)

    async def update_task_occurrence(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        original_starts_at: datetime,
        data: UpdateTaskOccurrence,
    ) -> TaskOccurrence:
        async with self.uow() as uow:
            template_id = await uow.task.get_recurrence_template_id(user_id, recurrence_id)
            occurrence = await uow.task.update_task_occurrence(
                user_id,
                recurrence_id,
                original_starts_at,
                data,
            )
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=occurrence.task_id or template_id,
                event_type=AuditEventType.TASK_OCCURRENCE_UPDATED,
                data={
                    "recurrence_id": str(recurrence_id),
                    "original_starts_at": original_starts_at.isoformat(),
                    "is_cancelled": occurrence.is_cancelled,
                },
            )
            return occurrence

    async def skip_task_occurrence(
        self, user_id: UUID, recurrence_id: UUID, original_starts_at: datetime
    ) -> TaskOccurrence:
        async with self.uow() as uow:
            template_id = await uow.task.get_recurrence_template_id(user_id, recurrence_id)
            occurrence = await uow.task.skip_task_occurrence(
                user_id, recurrence_id, original_starts_at
            )
            await self._record_task_event(
                uow,
                user_id=user_id,
                task_id=occurrence.task_id or template_id,
                event_type=AuditEventType.TASK_OCCURRENCE_SKIPPED,
                data={
                    "recurrence_id": str(recurrence_id),
                    "original_starts_at": original_starts_at.isoformat(),
                },
            )
            return occurrence

    # Checks

    async def _check_if_task_exists(self, uow, user_id: UUID, task_id: UUID) -> None:
        if not await uow.task.exists_task(user_id, task_id):
            raise app_exc.TaskNotFound

    async def _check_if_task_belongs_to_user(self, uow, user_id: UUID, task_id: UUID) -> None:
        if not await uow.task.exists_task_including_deleted(user_id, task_id):
            raise app_exc.TaskNotFound

    async def _check_if_tag_exists(self, uow, user_id: UUID, tag_id: UUID) -> None:
        if not await uow.tag.exists_tag(user_id, tag_id):
            raise app_exc.TagNotFound

    # Audit helpers

    @staticmethod
    async def _record_task_event(
        uow,
        *,
        user_id: UUID,
        task_id: UUID,
        event_type: AuditEventType,
        data: dict[str, Any] | None = None,
    ) -> None:
        await uow.audit.add_event(
            actor_user_id=user_id,
            entity_type=AuditEntityType.TASK,
            entity_id=task_id,
            event_type=event_type,
            data=data,
        )

    @staticmethod
    async def _record_task_events(
        uow,
        events: list[dict[str, Any]],
    ) -> None:
        await uow.audit.add_events(
            [
                {
                    "actor_user_id": event["user_id"],
                    "entity_type": AuditEntityType.TASK.value,
                    "entity_id": event["task_id"],
                    "event_type": event["event_type"].value,
                    "data": event.get("data") or {},
                }
                for event in events
            ]
        )

    # Data helpers

    @staticmethod
    def _changed_task_fields(data: UpdateTaskData) -> list[str]:
        fields = ("title", "description", "status", "priority", "due_at", "schedule")
        return [field for field in fields if getattr(data, field) is not None]

    @staticmethod
    def _validate_schedule_windows(windows: tuple[Schedule, ...]) -> None:
        for window in windows:
            if window.ends_at < window.starts_at:
                raise ValueError("ends_at cannot be earlier than starts_at")

    @classmethod
    def _prepare_schedule_windows(cls, windows: Iterable[Schedule]) -> tuple[Schedule, ...]:
        schedule_windows = tuple(windows)
        if not schedule_windows:
            raise ValueError("at least one schedule window is required")

        cls._validate_schedule_windows(schedule_windows)
        return schedule_windows

    @staticmethod
    def _materialization_windows_for_filters(filters: ListTasksFilters) -> tuple[Schedule, ...]:
        starts_at = filters.starts_from or filters.ends_from or datetime.now()
        ends_at = filters.ends_to or filters.starts_to or (starts_at + timedelta(days=365))
        if ends_at < starts_at:
            ends_at = starts_at
        return (Schedule(starts_at=starts_at, ends_at=ends_at),)
