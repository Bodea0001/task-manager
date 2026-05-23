from uuid import UUID
from datetime import datetime, timedelta
from dataclasses import asdict

from sqlalchemy import select, update, literal
from sqlalchemy.dialects.postgresql import insert as pg_insert

import exceptions as app_exc
from dto.tasks import UpdateTaskData, UpdateTaskOccurrence
from models.tasks import (
    Task as TaskModel,
    ScheduledTask as ScheduledTaskModel,
    TaskRecurrenceInstance as TaskRecurrenceInstanceModel,
    TaskRecurrenceInstanceOverride as TaskRecurrenceInstanceOverrideModel,
    TaskRecurrenceSeries as TaskRecurrenceSeriesModel,
    TaskRecurrenceTemplate as TaskRecurrenceTemplateModel,
)
from domain.value_objects.tasks import (
    Schedule,
    TaskStatus,
    TaskOccurrence,
    RecurrenceOverrideAction,
)
from adapters.repositories.task_repository_common import translate_repository_errors
from adapters.repositories.task_repository_recurrence import TaskRecurrenceMixin
from adapters.repositories.task_repository_schedule import TaskScheduleMixin


class TaskOccurrenceMixin(TaskRecurrenceMixin, TaskScheduleMixin):
    async def skip_task_occurrence(
        self, user_id: UUID, recurrence_id: UUID, original_starts_at: datetime
    ) -> TaskOccurrence:
        return await self.update_task_occurrence(
            user_id,
            recurrence_id,
            original_starts_at,
            UpdateTaskOccurrence(is_cancelled=True),
            override_action=RecurrenceOverrideAction.SKIP,
        )

    async def get_task_occurrences(
        self,
        user_id: UUID,
        template_id: UUID,
        window: Schedule,
    ) -> list[TaskOccurrence]:
        stmt = (
            self._select_task_occurrence_rows()
            .join(
                TaskRecurrenceSeriesModel,
                TaskRecurrenceSeriesModel.series_id == TaskRecurrenceInstanceModel.series_id,
            )
            .join(
                TaskRecurrenceTemplateModel,
                TaskRecurrenceTemplateModel.template_id == TaskRecurrenceSeriesModel.template_id,
            )
            .where(
                TaskModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.template_id == template_id,
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskModel.deleted_at.is_(None),
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
                ScheduledTaskModel.starts_at < window.ends_at,
                ScheduledTaskModel.ends_at > window.starts_at,
            )
            .order_by(ScheduledTaskModel.starts_at, ScheduledTaskModel.ends_at)
        )
        result = await self.session.execute(stmt)
        return [self._row_to_task_occurrence(row) for row in result.all()]

    async def get_recurrence_instance_by_task_id(
        self,
        user_id: UUID,
        task_id: UUID,
    ) -> TaskOccurrence | None:
        stmt = (
            self._select_task_occurrence_rows()
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id == task_id,
                TaskModel.deleted_at.is_(None),
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        return self._row_to_task_occurrence(row) if row is not None else None

    @translate_repository_errors
    async def update_task_occurrence(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        original_starts_at: datetime,
        data: UpdateTaskOccurrence,
        override_action: RecurrenceOverrideAction | None = None,
    ) -> TaskOccurrence:
        await self._raise_if_recurrence_does_not_belong_to_user(user_id, recurrence_id)
        task_id = await self._maybe_task_id_for_recurrence_occurrence(
            recurrence_id, original_starts_at
        )
        if task_id is None:
            await self._upsert_recurrence_occurrence_override(
                recurrence_id=recurrence_id,
                original_starts_at=original_starts_at,
                data=data,
                action=(
                    override_action
                    or (
                        RecurrenceOverrideAction.DELETE
                        if data.is_cancelled
                        else RecurrenceOverrideAction.MODIFY
                    )
                ),
            )
            schedule = data.schedule or await self._planned_schedule_for_recurrence_occurrence(
                recurrence_id,
                original_starts_at,
            )
            return TaskOccurrence(
                recurrence_id=recurrence_id,
                task_id=None,
                original_starts_at=original_starts_at,
                schedule=schedule,
                is_cancelled=data.is_cancelled,
            )
        if data.schedule is not None:
            await self._raise_if_schedule_overlaps(
                user_id,
                task_id=task_id,
                schedule=data.schedule,
            )
        if data.is_cancelled:
            task_update_data = UpdateTaskData(status=TaskStatus.CANCELLED)
        else:
            task_update_data = UpdateTaskData(
                title=data.title,
                description=data.description,
                status=data.status,
                priority=data.priority,
                due_at=data.due_at or (data.schedule.ends_at if data.schedule else None),
                schedule=data.schedule,
            )
        await self._update_task_and_recurrence_instance(
            user_id=user_id,
            task_id=task_id,
            recurrence_id=recurrence_id,
            task_update_data=task_update_data,
        )
        if data.schedule is not None:
            schedule = data.schedule
        else:
            schedule = await self._schedule_for_task(task_id)
        return TaskOccurrence(
            recurrence_id=recurrence_id,
            task_id=task_id,
            original_starts_at=original_starts_at,
            schedule=schedule,
            is_cancelled=data.is_cancelled,
        )

    async def _update_task_and_recurrence_instance(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        recurrence_id: UUID,
        task_update_data: UpdateTaskData,
    ) -> None:
        updated_task = (
            self._update_task_stmt(user_id, task_id, self._task_update_values(task_update_data))
            .returning(TaskModel.task_id)
            .cte("updated_occurrence_task")
        )
        ctes = [updated_task]
        update_prerequisite = select(1).select_from(updated_task).exists()

        if task_update_data.schedule is not None:
            schedule = task_update_data.schedule
            schedule_values = {"starts_at": schedule.starts_at, "ends_at": schedule.ends_at}
            upserted_schedule = (
                pg_insert(ScheduledTaskModel)
                .from_select(
                    (
                        ScheduledTaskModel.task_id,
                        ScheduledTaskModel.starts_at,
                        ScheduledTaskModel.ends_at,
                    ),
                    select(
                        updated_task.c.task_id,
                        literal(schedule.starts_at),
                        literal(schedule.ends_at),
                    ),
                )
                .on_conflict_do_update(index_elements=["task_id"], set_=schedule_values)
                .returning(ScheduledTaskModel.task_id)
                .cte("updated_occurrence_schedule")
            )
            ctes.append(upserted_schedule)
            update_prerequisite = select(1).select_from(upserted_schedule).exists()

        updated_instance = (
            update(TaskRecurrenceInstanceModel)
            .values(is_customized=True)
            .where(
                TaskRecurrenceInstanceModel.series_id == recurrence_id,
                TaskRecurrenceInstanceModel.task_id == task_id,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
                update_prerequisite,
            )
            .returning(TaskRecurrenceInstanceModel.instance_id)
            .cte("updated_occurrence_instance")
        )
        stmt = select(select(1).select_from(updated_instance).exists())
        for cte in ctes:
            stmt = stmt.add_cte(cte)

        result = await self.session.execute(stmt)
        if not result.scalar_one():
            raise app_exc.TaskNotFound

    async def _recurrence_instance_for_original_start(
        self,
        recurrence_id: UUID,
        original_starts_at: datetime,
    ) -> TaskRecurrenceInstanceModel:
        result = await self.session.execute(
            select(TaskRecurrenceInstanceModel).where(
                TaskRecurrenceInstanceModel.series_id == recurrence_id,
                TaskRecurrenceInstanceModel.planned_starts_at == original_starts_at,
                TaskRecurrenceInstanceModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def _task_id_for_recurrence_occurrence(
        self, recurrence_id: UUID, original_starts_at: datetime
    ) -> UUID:
        stmt = select(TaskRecurrenceInstanceModel.task_id).where(
            TaskRecurrenceInstanceModel.series_id == recurrence_id,
            TaskRecurrenceInstanceModel.planned_starts_at == original_starts_at,
            TaskRecurrenceInstanceModel.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _maybe_task_id_for_recurrence_occurrence(
        self, recurrence_id: UUID, original_starts_at: datetime
    ) -> UUID | None:
        stmt = select(TaskRecurrenceInstanceModel.task_id).where(
            TaskRecurrenceInstanceModel.series_id == recurrence_id,
            TaskRecurrenceInstanceModel.planned_starts_at == original_starts_at,
            TaskRecurrenceInstanceModel.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _planned_schedule_for_recurrence_occurrence(
        self,
        recurrence_id: UUID,
        original_starts_at: datetime,
    ) -> Schedule:
        result = await self.session.execute(
            select(
                TaskRecurrenceSeriesModel.default_duration,
            ).where(
                TaskRecurrenceSeriesModel.series_id == recurrence_id,
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
            )
        )
        duration = result.scalar_one() or timedelta(0)
        return Schedule(starts_at=original_starts_at, ends_at=original_starts_at + duration)

    async def _upsert_recurrence_occurrence_override(
        self,
        *,
        recurrence_id: UUID,
        original_starts_at: datetime,
        data: UpdateTaskOccurrence,
        action: RecurrenceOverrideAction,
    ) -> None:
        values = {
            "action": action,
            "override_starts_at": data.schedule.starts_at if data.schedule else None,
            "override_ends_at": data.schedule.ends_at if data.schedule else None,
            "override_title": data.title,
            "override_description": data.description,
            "override_due_at": data.due_at,
            "override_priority": data.priority,
            "patch": {
                key: value.value
                if hasattr(value, "value")
                else value.isoformat()
                if isinstance(value, datetime)
                else value
                for key, value in asdict(data).items()
                if value is not None and key not in {"schedule"}
            },
        }
        stmt = (
            pg_insert(TaskRecurrenceInstanceOverrideModel)
            .values(series_id=recurrence_id, planned_starts_at=original_starts_at, **values)
            .on_conflict_do_update(
                index_elements=["series_id", "planned_starts_at"],
                set_=values,
            )
        )
        await self.session.execute(stmt)

    async def _schedule_for_task(self, task_id: UUID) -> Schedule:
        result = await self.session.execute(
            select(ScheduledTaskModel).where(ScheduledTaskModel.task_id == task_id)
        )
        return self._model_to_schedule(result.scalar_one())
