from uuid import UUID
from typing import Sequence, Any, Concatenate, Final, ParamSpec, TypeVar, cast
from dataclasses import asdict
from collections.abc import Awaitable, Callable
from functools import wraps

import asyncpg
from sqlalchemy import Row, func, select, insert, update, delete, text
from sqlalchemy.orm import defer, selectinload
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.dialects.postgresql import insert as pg_insert

import exceptions as app_exc
from dto.tasks import ListTasksFilters, AddTask, UpdateTaskData
from models.tasks import TaskStore, Task as TaskModel, ScheduledTask as ScheduledTaskModel
from models.tags import Tag as TagModel
from models.task_tags import TaskTag as TaskTagModel
from domain.value_objects.tags import Tag as DomainTag
from domain.value_objects.tasks import FreeTime, Schedule, Task, TaskStatus
from adapters.repository import SQLAlchemyRepository


CORRECT_INTERVAL_CONSTRAINT = "ck_scheduled_task_correct_interval"
TASK_TAG_TASK_ID_FKEY = "fk_task_tag_task_id_task"
TASK_TAG_TAG_ID_FKEY = "fk_task_tag_tag_id_tag"
SCHEDULED_TASK_TASK_ID_FKEY = "fk_scheduled_task_task_id_task"
DESCRIPTION_NOT_LOADED: Final = cast(str | None, object())
P = ParamSpec("P")
R = TypeVar("R")


def translate_repository_errors(
    method: Callable[Concatenate["TaskRepository", P], Awaitable[R]],
) -> Callable[Concatenate["TaskRepository", P], Awaitable[R]]:
    @wraps(method)
    async def wrapper(self: "TaskRepository", /, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await method(self, *args, **kwargs)
        except NoResultFound:
            raise app_exc.TaskNotFound
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    return wrapper


class TaskRepository(SQLAlchemyRepository):
    async def get_tasks(self, filters: ListTasksFilters) -> list[Task]:
        stmt = (
            self._select_task_list_rows_with_tags()
            .where(*self._build_filters(filters))
            .order_by(*self._build_orders(filters))
            .limit(filters.limit)
            .offset(filters.offset)
        )

        for target, condition in self._joins_for_filters(filters):
            stmt = stmt.join(target, condition)

        result = await self.session.execute(stmt)
        return self._task_list_rows_to_tasks(result.all())

    async def count_tasks(self, filters: ListTasksFilters) -> int:
        stmt = select(func.count()).select_from(TaskModel).where(*self._build_filters(filters))

        for target, condition in self._joins_for_filters(filters):
            stmt = stmt.join(target, condition)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_overdue_tasks(self, limit: int, offset: int) -> list[Task]:
        stmt = (
            self._select_task_list_rows_with_tags()
            .where(TaskModel.due_at < func.now(), TaskModel.status == TaskStatus.ACTIVE)
            .order_by(TaskModel.due_at, TaskModel.created_at)
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return self._task_list_rows_to_tasks(result.all())

    async def get_free_time(self, window: Schedule) -> list[FreeTime]:
        stmt = text("""
            WITH busy AS (
                SELECT
                    greatest(starts_at, :starts_at) AS starts_at,
                    least(ends_at, :ends_at) AS ends_at
                FROM scheduled_task
                WHERE starts_at < :ends_at AND ends_at > :starts_at
            ),
            ordered_busy AS (
                SELECT
                    starts_at,
                    ends_at,
                    lead(starts_at) OVER (ORDER BY starts_at, ends_at) AS next_starts_at
                FROM busy
            ),
            gaps AS (
                SELECT :starts_at AS starts_at, min(starts_at) AS ends_at
                FROM busy
                HAVING count(*) > 0

                UNION ALL

                SELECT ends_at AS starts_at, next_starts_at AS ends_at
                FROM ordered_busy
                WHERE next_starts_at IS NOT NULL

                UNION ALL

                SELECT max(ends_at) AS starts_at, :ends_at AS ends_at
                FROM busy
                HAVING count(*) > 0

                UNION ALL

                SELECT :starts_at AS starts_at, :ends_at AS ends_at
                WHERE NOT EXISTS (SELECT 1 FROM busy)
            )
            SELECT starts_at, ends_at
            FROM gaps
            WHERE starts_at < ends_at
            ORDER BY starts_at, ends_at
        """)

        result = await self.session.execute(
            stmt,
            {"starts_at": window.starts_at, "ends_at": window.ends_at},
        )
        return [self._row_to_free_time(row) for row in result.all()]

    @translate_repository_errors
    async def get_task(self, task_id: UUID) -> Task:
        stmt = self._select_tasks_with_tags().where(TaskModel.task_id == task_id)

        result = await self.session.execute(stmt)
        return self._model_to_task(result.scalar_one())

    async def exists_task(self, task_id: UUID) -> bool:
        stmt = select(select(1).select_from(TaskModel).where(TaskModel.task_id == task_id).exists())
        result = await self.session.execute(stmt)
        return result.scalar_one()

    @translate_repository_errors
    async def add_task(self, data: AddTask) -> Task:
        values = self._task_insert_values(data)
        stmt = insert(TaskModel).values(**values).returning(TaskModel.task_id)

        result = await self.session.execute(stmt)
        task_id = result.scalar_one()
        await self._add_tags_to_task(task_id, data.tag_ids)
        await self._upsert_task_schedule(task_id, data.schedule)

        return await self.get_task(task_id)

    @translate_repository_errors
    async def add_tag_to_task(self, task_id: UUID, tag_id: UUID) -> None:
        await self._add_tags_to_task(task_id, (tag_id,))

    @translate_repository_errors
    async def add_schedule_to_task(self, task_id: UUID, schedule: Schedule) -> None:
        await self._upsert_task_schedule(task_id, schedule)

    @translate_repository_errors
    async def update_task(self, task_id: UUID, data: UpdateTaskData) -> Task:
        values = self._task_update_values(data)

        stmt = update(TaskModel).values(**values).where(TaskModel.task_id == task_id)

        if values:
            await self.session.execute(stmt)
        await self._upsert_task_schedule(task_id, data.schedule)
        return await self.get_task(task_id)

    async def delete_task(self, task_id: UUID) -> None:
        stmt = delete(TaskModel).where(TaskModel.task_id == task_id)

        await self.session.execute(stmt)

    async def delete_tag_from_task(self, task_id: UUID, tag_id: UUID) -> None:
        stmt = delete(TaskTagModel).where(
            TaskTagModel.task_id == task_id,
            TaskTagModel.tag_id == tag_id,
        )

        await self.session.execute(stmt)

    async def delete_schedule_from_task(self, task_id: UUID) -> None:
        stmt = delete(ScheduledTaskModel).where(ScheduledTaskModel.task_id == task_id)

        await self.session.execute(stmt)

    async def _add_tags_to_task(self, task_id: UUID, tag_ids: tuple[UUID, ...]) -> None:
        unique_tag_ids = set(tag_ids)

        if not unique_tag_ids:
            return

        stmt = (
            pg_insert(TaskTagModel)
            .values([{"task_id": task_id, "tag_id": tag_id} for tag_id in unique_tag_ids])
            .on_conflict_do_nothing(index_elements=["task_id", "tag_id"])
        )

        await self.session.execute(stmt)

    async def _upsert_task_schedule(self, task_id: UUID, schedule: Schedule | None):
        if not schedule:
            return

        await self._raise_if_schedule_overlaps(task_id, schedule)

        values = asdict(schedule)

        stmt = (
            pg_insert(ScheduledTaskModel)
            .values(task_id=task_id, **values)
            .on_conflict_do_update(index_elements=["task_id"], set_=values)
        )

        await self.session.execute(stmt)

    async def _raise_if_schedule_overlaps(self, task_id: UUID, schedule: Schedule) -> None:
        stmt = select(
            select(1)
            .select_from(ScheduledTaskModel)
            .where(
                ScheduledTaskModel.task_id != task_id,
                ScheduledTaskModel.starts_at < schedule.ends_at,
                ScheduledTaskModel.ends_at > schedule.starts_at,
            )
            .exists()
        )

        result = await self.session.execute(stmt)
        if result.scalar_one():
            raise app_exc.TaskScheduleOverlap

    @staticmethod
    def _select_tasks_with_tags():
        return select(TaskModel).options(selectinload(TaskModel.tags))

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
    def _short_description_expr():
        return func.substring(TaskModel.description, 0, 37).op("||")("...")

    @staticmethod
    def _task_insert_values(data: AddTask) -> dict[str, Any]:
        return {k: v for k, v in asdict(data).items() if k not in {"tag_ids", "schedule"}}

    @staticmethod
    def _task_update_values(data: UpdateTaskData) -> dict[str, Any]:
        return {k: v for k, v in asdict(data).items() if v is not None and k != "schedule"}

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
        if filters.tag_ids:
            conditions.append(
                select(1)
                .select_from(TaskTagModel)
                .where(
                    TaskTagModel.task_id == TaskModel.task_id,
                    TaskTagModel.tag_id.in_(filters.tag_ids),
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

        if TaskRepository._has_schedule_filters(filters):
            orders.append(ScheduledTaskModel.starts_at.nulls_last())
        else:
            orders.extend((TaskModel.due_at, TaskModel.created_at))

        return orders

    @staticmethod
    def _joins_for_filters(filters: ListTasksFilters):
        joins = []

        if TaskRepository._has_schedule_filters(filters):
            joins.append((ScheduledTaskModel, ScheduledTaskModel.task_id == TaskModel.task_id))

        if filters.search_text:
            joins.append((TaskStore, TaskStore.task_id == TaskModel.task_id))

        return joins

    @staticmethod
    def _has_schedule_filters(filters: ListTasksFilters) -> bool:
        return any((filters.starts_from, filters.starts_to, filters.ends_from, filters.ends_to))

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
            TaskRepository._model_to_task(
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

        tags = [TaskRepository._model_to_tag(tag) for tag in model.tags]

        schedule = TaskRepository._model_to_schedule(model.schedule) if model.schedule else None

        return Task(
            task_id=model.task_id,
            title=model.title,
            description=description,
            due_at=model.due_at,
            status=model.status,
            created_at=model.created_at,
            completed_at=model.completed_at,
            schedule=schedule,
            tags=tags,
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
    def _row_to_free_time(row: Row[Any]) -> FreeTime:
        return FreeTime(starts_at=row.starts_at, ends_at=row.ends_at)
