from uuid import UUID
from typing import Any
from dataclasses import asdict

import asyncpg
from sqlalchemy import text, select, insert, update, delete
from sqlalchemy.exc import IntegrityError, NoResultFound

import exceptions as app_exc
from dto.tasks import ListTasksFilters, AddTask, UpdateTaskData
from models.tasks import Task as TaskModel
from domain.value_objects.tasks import Task, TaskStatus
from adapters.repository import SQLAlchemyRepository


TASK_LIST_COLUMNS = """
    task_id,
    title,
    SUBSTRING(description from 0 for 37) || '...' AS description,
    status,
    starts_at,
    ends_at,
    created_at,
    completed_at
"""
ORDER_TASKS_BY_DEADLINE = "ORDER BY ends_at, starts_at, created_at"
CORRECT_DEADLINE_CONSTRAINT = "ck_task_correct_deadline"


class TaskRepository(SQLAlchemyRepository):
    async def get_tasks(self, filters: ListTasksFilters) -> list[Task]:
        where_stmt, params = self._build_filters(filters)
        params.update({"limit": filters.limit, "offset": filters.offset})

        stmt = text(f"""
            SELECT {TASK_LIST_COLUMNS}
            FROM task
            {where_stmt}
            {ORDER_TASKS_BY_DEADLINE}
            LIMIT :limit
            OFFSET :offset
        """)

        result = await self.session.execute(stmt, params=params)
        return self._rows_to_tasks(result.all())

    async def count_tasks(self, filters: ListTasksFilters) -> int:
        where_stmt, params = self._build_filters(filters)

        stmt = text(f"""
            SELECT COUNT(*)
            FROM task
            {where_stmt}
        """)

        result = await self.session.execute(stmt, params=params)
        return result.scalar_one()

    async def get_overdue_tasks(self, limit: int, offset: int) -> list[Task]:
        stmt = text(
            """
            SELECT """
            + TASK_LIST_COLUMNS
            + """
            FROM task
            WHERE
                ends_at < NOW() AND
                status = :status
            """
            + ORDER_TASKS_BY_DEADLINE
            + """
            LIMIT :limit
            OFFSET :offset
        """
        )

        result = await self.session.execute(
            stmt,
            {
                "status": TaskStatus.ACTIVE.value,
                "limit": limit,
                "offset": offset,
            },
        )
        return self._rows_to_tasks(result.all())

    async def get_task(self, task_id: UUID) -> Task:
        stmt = select(TaskModel).where(TaskModel.task_id == task_id)

        try:
            result = await self.session.execute(stmt)
            return self._model_to_task(result.scalar_one())
        except NoResultFound:
            raise app_exc.TaskNotFound

    async def exists_task(self, task_id: UUID) -> bool:
        stmt = select(select(1).select_from(TaskModel).where(TaskModel.task_id == task_id).exists())
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def add_task(self, data: AddTask) -> Task:
        values = {k: v for k, v in asdict(data).items()}
        stmt = insert(TaskModel).values(**values).returning(TaskModel)

        try:
            result = await self.session.execute(stmt)
            return self._model_to_task(result.scalar_one())
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    async def update_task(self, task_id: UUID, data: UpdateTaskData) -> Task:
        values = {key: value for key, value in asdict(data).items() if value is not None}
        stmt = (
            update(TaskModel)
            .values(**values)
            .where(TaskModel.task_id == task_id)
            .returning(TaskModel)
        )

        try:
            result = await self.session.execute(stmt)
            return self._model_to_task(result.scalar_one())
        except NoResultFound:
            raise app_exc.TaskNotFound
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    async def delete_task(self, task_id: UUID) -> None:
        stmt = delete(TaskModel).where(TaskModel.task_id == task_id)

        await self.session.execute(stmt)

    @staticmethod
    def _build_filters(filters: ListTasksFilters) -> tuple[str, dict[str, Any]]:
        conditions = []
        params = {}

        if filters.starts_from:
            conditions.append("starts_at >= :starts_from")
            params["starts_from"] = filters.starts_from

        if filters.starts_to:
            conditions.append("starts_at <= :starts_to")
            params["starts_to"] = filters.starts_to

        if filters.ends_from:
            conditions.append("ends_at >= :ends_from")
            params["ends_from"] = filters.ends_from

        if filters.ends_to:
            conditions.append("ends_at <= :ends_to")
            params["ends_to"] = filters.ends_to

        if filters.statuses:
            conditions.append("status = ANY(:statuses)")
            params["statuses"] = [status.value for status in filters.statuses]

        if not conditions:
            return "", params

        return "WHERE " + " AND ".join(conditions), params

    @staticmethod
    def _raise_app_error_for_integrity_error(error: IntegrityError) -> None:
        driver_exc = getattr(error.orig, "__cause__", None)

        if not isinstance(driver_exc, asyncpg.exceptions.CheckViolationError):
            return

        if CORRECT_DEADLINE_CONSTRAINT in str(error.orig):
            raise app_exc.WrongTaskDeadline

    @staticmethod
    def _rows_to_tasks(rows) -> list[Task]:
        return [Task.from_dict(row._asdict()) for row in rows]

    @staticmethod
    def _model_to_task(model: TaskModel) -> Task:
        return Task(
            task_id=model.task_id,
            title=model.title,
            description=model.description,
            status=model.status,
            starts_at=model.starts_at,
            ends_at=model.ends_at,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )
