import json
from uuid import UUID
from typing import Sequence, Any, Concatenate, Final, ParamSpec, TypeVar, cast
from datetime import datetime, time, timedelta
from functools import wraps
from dataclasses import asdict
from collections.abc import Awaitable, Callable

import asyncpg
from sqlalchemy import (
    Row,
    func,
    select,
    update,
)
from sqlalchemy.orm import defer, selectinload
from sqlalchemy.exc import IntegrityError, NoResultFound

import exceptions as app_exc
from config import settings
from dto.tasks import (
    AddTask,
    UpdateTaskData,
    ListTasksFilters,
    AddTaskRecurrence,
    UpdateTaskRecurrence,
    ListTaskRecurrenceTemplatesFilters,
)
from models.tags import Tag as TagModel
from models.tasks import (
    TaskStore,
    Task as TaskModel,
    ScheduledTask as ScheduledTaskModel,
    TaskRecurrenceSeries as TaskRecurrenceSeriesModel,
    TaskRecurrenceInstance as TaskRecurrenceInstanceModel,
    TaskRecurrenceTemplate as TaskRecurrenceTemplateModel,
)
from models.task_tags import TaskTag as TaskTagModel
from domain.recurrences import recurrence_end_mode
from domain.value_objects.tags import Tag as DomainTag
from domain.value_objects.tasks import (
    Task,
    Schedule,
    FreeTime,
    TaskKind,
    TaskStatus,
    TaskPriority,
    TaskOccurrence,
    TaskRecurrence,
    RecurrenceFrequency,
    TaskRecurrenceTemplate,
)
from adapters.repository import SQLAlchemyRepository


CORRECT_INTERVAL_CONSTRAINT = "ck_scheduled_task_correct_interval"
TASK_TAG_TASK_ID_FKEY = "fk_task_tag_task_id_task"
TASK_TAG_TAG_ID_FKEY = "fk_task_tag_tag_id_tag"
SCHEDULED_TASK_TASK_ID_FKEY = "fk_scheduled_task_task_id_task"
DESCRIPTION_NOT_LOADED: Final = cast(str | None, object())
P = ParamSpec("P")
R = TypeVar("R")


def translate_repository_errors(
    method: Callable[Concatenate[Any, P], Awaitable[R]],
) -> Callable[Concatenate[Any, P], Awaitable[R]]:
    @wraps(method)
    async def wrapper(self: Any, /, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await method(self, *args, **kwargs)
        except NoResultFound:
            raise app_exc.TaskNotFound
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    return wrapper


class TaskRepositoryCommon(SQLAlchemyRepository):
    @staticmethod
    def _select_tasks_with_tags():
        return select(TaskModel).options(selectinload(TaskModel.tags))

    @staticmethod
    def _task_is_not_deleted():
        return TaskModel.deleted_at.is_(None)

    @staticmethod
    def _tag_is_not_deleted():
        return TagModel.deleted_at.is_(None)

    @classmethod
    def _select_task_list_rows_with_tags(cls):
        return (
            select(
                TaskModel,
                cls._short_description_expr().label("short_description"),
            )
            .select_from(TaskModel)
            .options(
                defer(TaskModel.description),
                selectinload(TaskModel.tags),
            )
        )

    @staticmethod
    def _select_task_occurrence_rows():
        return (
            select(
                TaskRecurrenceInstanceModel.series_id.label("recurrence_id"),
                TaskRecurrenceInstanceModel.task_id,
                TaskRecurrenceInstanceModel.planned_starts_at.label("original_starts_at"),
                ScheduledTaskModel.starts_at,
                ScheduledTaskModel.ends_at,
                (TaskModel.status == TaskStatus.CANCELLED).label("is_cancelled"),
            )
            .select_from(TaskRecurrenceInstanceModel)
            .join(TaskModel, TaskModel.task_id == TaskRecurrenceInstanceModel.task_id)
            .join(ScheduledTaskModel, ScheduledTaskModel.task_id == TaskModel.task_id)
        )

    @staticmethod
    def _short_description_expr():
        return func.substring(TaskModel.description, 0, 37).op("||")("...")

    @staticmethod
    def _task_insert_values(data: AddTask) -> dict[str, Any]:
        return {k: v for k, v in asdict(data).items() if k not in {"tag_ids", "schedule"}}

    @staticmethod
    def _task_update_values(data: UpdateTaskData) -> dict[str, Any]:
        return {k: v for k, v in asdict(data).items() if v is not None and k != "schedule"}

    @classmethod
    def _update_task_stmt(cls, user_id: UUID, task_id: UUID, values: dict[str, Any]):
        return (
            update(TaskModel)
            .values(**values)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id == task_id,
                cls._task_is_not_deleted(),
            )
        )

    @staticmethod
    def _recurrence_update_values(
        data: AddTaskRecurrence | UpdateTaskRecurrence,
        *,
        frequency: RecurrenceFrequency | None = None,
        interval: int | None = None,
    ) -> dict[str, Any]:
        if isinstance(data, AddTaskRecurrence):
            frequency = data.frequency
            interval = data.interval
        if frequency is None or interval is None:
            raise ValueError("recurrence frequency and interval are required")

        return {
            "frequency": frequency,
            "step": interval,
            "anchor_date": data.schedule.starts_at.date(),
            "default_time": data.schedule.starts_at.time(),
            "default_duration": data.schedule.ends_at - data.schedule.starts_at,
            "end_mode": recurrence_end_mode(
                repeat_until=data.repeat_until,
                max_occurrences=data.occurrences_limit,
            ),
            "repeat_until": data.repeat_until.date() if data.repeat_until else None,
            "max_occurrences": data.occurrences_limit,
            "generation_finished_at": None,
            "generation_stop_reason": None,
        }

    @staticmethod
    def _recurrence_returning_columns():
        return (
            TaskRecurrenceSeriesModel.series_id,
            TaskRecurrenceSeriesModel.template_id,
            TaskRecurrenceSeriesModel.frequency,
            TaskRecurrenceSeriesModel.step,
            TaskRecurrenceSeriesModel.anchor_date,
            TaskRecurrenceSeriesModel.default_time,
            TaskRecurrenceSeriesModel.default_duration,
            TaskRecurrenceSeriesModel.repeat_until,
            TaskRecurrenceSeriesModel.max_occurrences,
        )

    @staticmethod
    def _initial_materialization_window(
        data: AddTaskRecurrence | UpdateTaskRecurrence,
        *,
        frequency: RecurrenceFrequency | None = None,
    ) -> Schedule:
        if isinstance(data, AddTaskRecurrence):
            frequency = data.frequency
        if frequency is None:
            raise ValueError("recurrence frequency is required")

        days = {
            RecurrenceFrequency.DAILY: settings.recurrence.daily_materialization_days,
            RecurrenceFrequency.WEEKLY: settings.recurrence.weekly_materialization_days,
            RecurrenceFrequency.MONTHLY: settings.recurrence.monthly_materialization_days,
        }[frequency]
        return Schedule(
            starts_at=data.schedule.starts_at,
            ends_at=data.schedule.starts_at + timedelta(days=days),
        )

    @staticmethod
    def _recurrence_rules_json(rules: tuple[AddTaskRecurrence, ...]) -> str:
        return json.dumps(
            [
                {
                    "frequency": rule.frequency.value,
                    "interval": rule.interval,
                    "starts_at": rule.schedule.starts_at.isoformat(),
                    "ends_at": rule.schedule.ends_at.isoformat(),
                    "repeat_until": rule.repeat_until.isoformat()
                    if rule.repeat_until is not None
                    else None,
                    "occurrences_limit": rule.occurrences_limit,
                }
                for rule in rules
            ]
        )

    @staticmethod
    def _build_filters(filters: ListTasksFilters):
        conditions = []

        if filters.due_from:
            conditions.append(TaskModel.due_at >= filters.due_from)
        if filters.due_to:
            conditions.append(TaskModel.due_at <= filters.due_to)
        if filters.starts_from:
            conditions.append(ScheduledTaskModel.starts_at >= filters.starts_from)
        if filters.starts_to:
            conditions.append(ScheduledTaskModel.starts_at <= filters.starts_to)
        if filters.ends_from:
            conditions.append(ScheduledTaskModel.ends_at >= filters.ends_from)
        if filters.ends_to:
            conditions.append(ScheduledTaskModel.ends_at <= filters.ends_to)
        if filters.statuses:
            conditions.append(TaskModel.status.in_(filters.statuses))
        if filters.priorities:
            conditions.append(TaskModel.priority.in_(filters.priorities))
        if filters.tag_ids:
            conditions.append(
                select(1)
                .select_from(TaskTagModel)
                .where(
                    TaskTagModel.task_id == TaskModel.task_id,
                    TaskTagModel.tag_id.in_(filters.tag_ids),
                    select(1)
                    .select_from(TagModel)
                    .where(
                        TagModel.tag_id == TaskTagModel.tag_id,
                        TaskRepositoryCommon._tag_is_not_deleted(),
                    )
                    .exists(),
                )
                .exists()
            )
        if filters.search_text:
            conditions.append(
                TaskStore.tsv_content.bool_op("@@")(
                    func.websearch_to_tsquery("russian", filters.search_text)
                )
            )

        return conditions

    @staticmethod
    def _build_orders(filters: ListTasksFilters):
        orders = []

        if TaskRepositoryCommon._has_schedule_filters(filters):
            orders.append(ScheduledTaskModel.starts_at.nulls_last())
        else:
            orders.extend((TaskModel.due_at, TaskModel.created_at))

        return orders

    @staticmethod
    def _joins_for_filters(filters: ListTasksFilters):
        joins = []

        if TaskRepositoryCommon._has_schedule_filters(filters):
            joins.append((ScheduledTaskModel, ScheduledTaskModel.task_id == TaskModel.task_id))

        if filters.search_text:
            joins.append((TaskStore, TaskStore.task_id == TaskModel.task_id))

        return joins

    @staticmethod
    def _has_schedule_filters(filters: ListTasksFilters) -> bool:
        return any((filters.starts_from, filters.starts_to, filters.ends_from, filters.ends_to))

    @classmethod
    def _recurring_visibility_filters(cls, filters: ListTasksFilters):
        if filters.include_recurring:
            return [
                ~select(1)
                .select_from(TaskRecurrenceInstanceModel)
                .where(
                    TaskRecurrenceInstanceModel.task_id == TaskModel.task_id,
                    TaskModel.status == TaskStatus.CANCELLED,
                )
                .exists()
            ]

        return [
            ~select(1)
            .select_from(TaskRecurrenceInstanceModel)
            .where(TaskRecurrenceInstanceModel.task_id == TaskModel.task_id)
            .exists()
        ]

    @staticmethod
    def _build_recurrence_template_filters(filters: ListTaskRecurrenceTemplatesFilters):
        conditions = []

        if filters.priorities:
            conditions.append(TaskRecurrenceTemplateModel.priority.in_(filters.priorities))
        if filters.frequencies:
            conditions.append(
                select(1)
                .select_from(TaskRecurrenceSeriesModel)
                .where(
                    TaskRecurrenceSeriesModel.template_id
                    == TaskRecurrenceTemplateModel.template_id,
                    TaskRecurrenceSeriesModel.frequency.in_(filters.frequencies),
                    TaskRecurrenceSeriesModel.deleted_at.is_(None),
                )
                .exists()
            )
        return conditions

    @staticmethod
    def _raise_app_error_for_integrity_error(error: IntegrityError) -> None:
        driver_exc = getattr(error.orig, "__cause__", None)

        if isinstance(driver_exc, asyncpg.exceptions.CheckViolationError):
            if CORRECT_INTERVAL_CONSTRAINT in str(error.orig):
                raise app_exc.WrongTaskInterval

        if isinstance(driver_exc, asyncpg.exceptions.ForeignKeyViolationError):
            str_error = str(error.orig)

            if TASK_TAG_TASK_ID_FKEY in str_error:
                raise app_exc.TaskNotFound

            if TASK_TAG_TAG_ID_FKEY in str_error:
                raise app_exc.TagNotFound

            if SCHEDULED_TASK_TASK_ID_FKEY in str_error:
                raise app_exc.TaskNotFound

    @staticmethod
    def _task_list_rows_to_tasks(rows: Sequence[Row[tuple[TaskModel, Any]]]) -> list[Task]:
        return [
            TaskRepositoryCommon._model_to_task(
                row[0],
                short_description=row.short_description,
            )
            for row in rows
        ]

    @staticmethod
    def _model_to_task(
        model: TaskModel,
        short_description: str | None = DESCRIPTION_NOT_LOADED,
    ) -> Task:
        if short_description is DESCRIPTION_NOT_LOADED:
            description = model.description
        else:
            description = short_description

        tags = [
            TaskRepositoryCommon._model_to_tag(tag) for tag in model.tags if tag.deleted_at is None
        ]

        schedule = (
            TaskRepositoryCommon._model_to_schedule(model.schedule) if model.schedule else None
        )

        return Task(
            task_id=model.task_id,
            title=model.title,
            description=description,
            due_at=model.due_at,
            status=model.status,
            priority=model.priority,
            created_at=model.created_at,
            completed_at=model.completed_at,
            schedule=schedule,
            tags=tags,
        )

    @staticmethod
    def _row_to_recurrence_conflict_task(row: Row[Any]) -> Task:
        return Task(
            task_id=row.conflict_id,
            title=row.title,
            description=row.description or row.reason,
            due_at=row.planned_ends_at,
            status=TaskStatus.ACTIVE,
            priority=TaskPriority(row.priority),
            created_at=row.created_at,
            completed_at=None,
            schedule=Schedule(starts_at=row.planned_starts_at, ends_at=row.planned_ends_at),
            tags=[],
            kind=TaskKind.RECURRENCE_CONFLICT,
            recurrence_id=row.series_id,
        )

    @staticmethod
    def _model_to_tag(model: TagModel) -> DomainTag:
        return DomainTag(
            tag_id=model.tag_id,
            name=model.name,
            created_at=model.created_at,
        )

    @staticmethod
    def _model_to_schedule(model: ScheduledTaskModel) -> Schedule:
        return Schedule(starts_at=model.starts_at, ends_at=model.ends_at)

    @staticmethod
    def _model_to_recurrence_template(
        model: TaskRecurrenceTemplateModel,
    ) -> TaskRecurrenceTemplate:
        return TaskRecurrenceTemplate(
            template_id=model.template_id,
            title=model.title,
            description=model.description,
            priority=model.priority,
            created_at=model.created_at,
        )

    @classmethod
    def _rows_to_recurrence_template(cls, rows: Sequence[Row[Any]]) -> TaskRecurrenceTemplate:
        first_row = rows[0]
        return TaskRecurrenceTemplate(
            template_id=first_row.template_id,
            title=first_row.title,
            description=first_row.description,
            priority=TaskPriority(first_row.priority),
            created_at=first_row.created_at,
            rules=tuple(cls._row_to_recurrence(row) for row in rows if row.series_id is not None),
        )

    @classmethod
    def _rows_to_recurrence_templates(
        cls, rows: Sequence[Row[Any]]
    ) -> list[TaskRecurrenceTemplate]:
        rows_by_template_id: dict[UUID, list[Row[Any]]] = {}
        for row in rows:
            rows_by_template_id.setdefault(row.template_id, []).append(row)

        return [
            cls._rows_to_recurrence_template(template_rows)
            for template_rows in rows_by_template_id.values()
        ]

    @staticmethod
    def _model_to_recurrence(model: TaskRecurrenceSeriesModel) -> TaskRecurrence:
        starts_at = datetime.combine(model.anchor_date, model.default_time or time.min)
        ends_at = starts_at + (model.default_duration or timedelta(0))
        return TaskRecurrence(
            recurrence_id=model.series_id,
            template_id=model.template_id,
            frequency=model.frequency,
            interval=model.step,
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
            repeat_until=datetime.combine(model.repeat_until, time.min)
            if model.repeat_until is not None
            else None,
            occurrences_limit=model.max_occurrences,
        )

    @staticmethod
    def _row_to_recurrence(row: Row[Any]) -> TaskRecurrence:
        starts_at = datetime.combine(row.anchor_date, row.default_time or time.min)
        ends_at = starts_at + (row.default_duration or timedelta(0))
        return TaskRecurrence(
            recurrence_id=row.series_id,
            template_id=row.template_id,
            frequency=RecurrenceFrequency(row.frequency),
            interval=row.step,
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
            repeat_until=datetime.combine(row.repeat_until, time.min)
            if row.repeat_until is not None
            else None,
            occurrences_limit=row.max_occurrences,
        )

    @staticmethod
    def _row_to_free_time(row: Row[Any]) -> FreeTime:
        return FreeTime(starts_at=row.starts_at, ends_at=row.ends_at)

    @staticmethod
    def _row_to_schedule(row: Row[Any]) -> Schedule:
        return Schedule(starts_at=row.starts_at, ends_at=row.ends_at)

    @staticmethod
    def _row_to_task_occurrence(row: Row[Any]) -> TaskOccurrence:
        return TaskOccurrence(
            recurrence_id=row.recurrence_id,
            task_id=row.task_id,
            original_starts_at=row.original_starts_at,
            schedule=Schedule(starts_at=row.starts_at, ends_at=row.ends_at),
            is_cancelled=row.is_cancelled,
        )
