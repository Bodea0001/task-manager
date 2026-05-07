from uuid import UUID
from typing import Sequence, Any
from dataclasses import asdict

import asyncpg
from sqlalchemy import Row, func, select, insert, update, delete
from sqlalchemy.orm import defer, selectinload
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.dialects.postgresql import insert as pg_insert

import exceptions as app_exc
from dto.tasks import ListTasksFilters, AddTask, UpdateTaskData
from models.tasks import TaskStore, Task as TaskModel
from models.tags import Tag as TagModel
from models.task_tags import TaskTag as TaskTagModel
from domain.value_objects.tags import Tag as DomainTag
from domain.value_objects.tasks import Task, TaskStatus
from adapters.repository import SQLAlchemyRepository


CORRECT_DEADLINE_CONSTRAINT = "ck_task_correct_deadline"
TASK_TAG_TASK_ID_FKEY = "fk_task_tag_task_id_task"
TASK_TAG_TAG_ID_FKEY = "fk_task_tag_tag_id_tag"


class TaskRepository(SQLAlchemyRepository):
    async def get_tasks(self, filters: ListTasksFilters) -> list[Task]:
        stmt = (
            self._select_task_list_rows_with_tags()
            .where(*self._build_filters(filters))
            .order_by(TaskModel.ends_at, TaskModel.starts_at, TaskModel.created_at)
            .limit(filters.limit)
            .offset(filters.offset)
        )

        result = await self.session.execute(stmt)
        return self._task_list_rows_to_tasks(result.all())

    async def count_tasks(self, filters: ListTasksFilters) -> int:
        stmt = select(func.count()).select_from(TaskModel).where(*self._build_filters(filters))

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_overdue_tasks(self, limit: int, offset: int) -> list[Task]:
        stmt = (
            self._select_task_list_rows_with_tags()
            .where(TaskModel.ends_at < func.now(), TaskModel.status == TaskStatus.ACTIVE)
            .order_by(TaskModel.ends_at, TaskModel.starts_at, TaskModel.created_at)
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return self._task_list_rows_to_tasks(result.all())

    async def get_task(self, task_id: UUID) -> Task:
        stmt = self._select_tasks_with_tags().where(TaskModel.task_id == task_id)

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
        values = {k: v for k, v in asdict(data).items() if k != "tag_ids"}
        stmt = insert(TaskModel).values(**values).returning(TaskModel)

        try:
            result = await self.session.execute(stmt)
            task_model = result.scalar_one()
            await self._add_tags_to_task(task_model.task_id, data.tag_ids)

            if data.tag_ids:
                tags = await self._get_tags(data.tag_ids)
                return self._model_to_task(task_model, tags=tags)

            return self._model_to_task(task_model, include_tags=False)
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
            return self._model_to_task(result.scalar_one(), include_tags=False)
        except NoResultFound:
            raise app_exc.TaskNotFound
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    async def delete_task(self, task_id: UUID) -> None:
        stmt = delete(TaskModel).where(TaskModel.task_id == task_id)

        await self.session.execute(stmt)

    async def add_tag_to_task(self, task_id: UUID, tag_id: UUID) -> None:
        await self._add_tags_to_task(task_id, (tag_id,))

    async def _add_tags_to_task(self, task_id: UUID, tag_ids: tuple[UUID, ...]) -> None:
        unique_tag_ids = set(tag_ids)

        if not unique_tag_ids:
            return

        stmt = (
            pg_insert(TaskTagModel)
            .values([{"task_id": task_id, "tag_id": tag_id} for tag_id in unique_tag_ids])
            .on_conflict_do_nothing(index_elements=["task_id", "tag_id"])
        )

        try:
            await self.session.execute(stmt)
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    async def _get_tags(self, tag_ids: tuple[UUID, ...]) -> list[DomainTag]:
        if not tag_ids:
            return []

        stmt = select(TagModel).where(TagModel.tag_id.in_(tag_ids)).order_by(TagModel.name)

        result = await self.session.execute(stmt)
        return [self._model_to_tag(tag) for tag in result.scalars()]

    async def delete_tag_from_task(self, task_id: UUID, tag_id: UUID) -> None:
        stmt = delete(TaskTagModel).where(
            TaskTagModel.task_id == task_id,
            TaskTagModel.tag_id == tag_id,
        )

        await self.session.execute(stmt)

    @staticmethod
    def _select_tasks_with_tags():
        return select(TaskModel).options(selectinload(TaskModel.tags))

    @classmethod
    def _select_task_list_rows_with_tags(cls):
        return select(
            TaskModel,
            cls._short_description().label("short_description"),
        ).options(
            defer(TaskModel.description),
            selectinload(TaskModel.tags),
        )

    @staticmethod
    def _short_description():
        return func.substring(TaskModel.description, 0, 37).op("||")("...")

    @staticmethod
    def _build_filters(filters: ListTasksFilters):
        conditions = []

        if filters.starts_from:
            conditions.append(TaskModel.starts_at >= filters.starts_from)

        if filters.starts_to:
            conditions.append(TaskModel.starts_at <= filters.starts_to)

        if filters.ends_from:
            conditions.append(TaskModel.ends_at >= filters.ends_from)

        if filters.ends_to:
            conditions.append(TaskModel.ends_at <= filters.ends_to)

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
                select(1)
                .select_from(TaskStore)
                .where(
                    TaskStore.task_id == TaskModel.task_id,
                    TaskStore.tsv_content.bool_op("@@")(
                        func.websearch_to_tsquery("russian", filters.search_text)
                    ),
                )
                .exists()
            )

        return conditions

    @staticmethod
    def _raise_app_error_for_integrity_error(error: IntegrityError) -> None:
        driver_exc = getattr(error.orig, "__cause__", None)

        if isinstance(driver_exc, asyncpg.exceptions.CheckViolationError):
            if CORRECT_DEADLINE_CONSTRAINT in str(error.orig):
                raise app_exc.WrongTaskDeadline

        if isinstance(driver_exc, asyncpg.exceptions.ForeignKeyViolationError):
            if TASK_TAG_TASK_ID_FKEY in str(error.orig):
                raise app_exc.TaskNotFound

            if TASK_TAG_TAG_ID_FKEY in str(error.orig):
                raise app_exc.TagNotFound

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
        short_description: str | None = None,
        include_tags: bool = True,
        tags: list[DomainTag] | None = None,
    ) -> Task:
        if short_description is not None:
            description = short_description
        else:
            description = model.description

        if tags is None:
            tags = []

            if include_tags:
                tags = [TaskRepository._model_to_tag(tag) for tag in model.tags]

        return Task(
            task_id=model.task_id,
            title=model.title,
            description=description,
            status=model.status,
            starts_at=model.starts_at,
            ends_at=model.ends_at,
            created_at=model.created_at,
            completed_at=model.completed_at,
            tags=tags,
        )

    @staticmethod
    def _model_to_tag(model) -> DomainTag:
        return DomainTag(
            tag_id=model.tag_id,
            name=model.name,
            created_at=model.created_at,
        )
