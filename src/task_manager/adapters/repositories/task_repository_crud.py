from uuid import UUID

from sqlalchemy import delete, false, func, insert, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from dto.tasks import AddTask, ListTasksFilters, TaskList, UpdateTaskData
from models.tags import Tag as TagModel
from models.tasks import (
    Task as TaskModel,
    ScheduledTask as ScheduledTaskModel,
    TaskRecurrenceMaterializationConflict as TaskRecurrenceMaterializationConflictModel,
    TaskRecurrenceSeries as TaskRecurrenceSeriesModel,
    TaskRecurrenceTemplate as TaskRecurrenceTemplateModel,
)
from models.task_tags import TaskTag as TaskTagModel
from domain.value_objects.tasks import Task, TaskStatus
from adapters.repositories.task_repository_common import translate_repository_errors
from adapters.repositories.task_repository_schedule import TaskScheduleMixin


class TaskCrudMixin(TaskScheduleMixin):
    async def get_tasks(self, user_id: UUID, filters: ListTasksFilters) -> TaskList:
        stmt = (
            self._select_task_list_rows_with_tags()
            .where(
                TaskModel.creator_id == user_id,
                self._task_is_not_deleted(),
                *self._recurring_visibility_filters(filters),
                *self._build_filters(filters),
            )
            .order_by(*self._build_orders(filters))
        )

        for target, condition in self._joins_for_filters(filters):
            stmt = stmt.join(target, condition)

        stmt = stmt.limit(filters.limit).offset(filters.offset)

        result = await self.session.execute(stmt)
        tasks = self._task_list_rows_to_tasks(result.all())
        conflicts = await self._get_recurrence_conflicts_as_tasks(user_id, filters)
        return TaskList(tasks=tasks, conflicts=conflicts)

    async def count_tasks(self, user_id: UUID, filters: ListTasksFilters) -> int:
        stmt = (
            select(func.count())
            .select_from(TaskModel)
            .where(
                TaskModel.creator_id == user_id,
                self._task_is_not_deleted(),
                *self._recurring_visibility_filters(filters),
                *self._build_filters(filters),
            )
        )

        for target, condition in self._joins_for_filters(filters):
            stmt = stmt.join(target, condition)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_overdue_tasks(self, user_id: UUID, limit: int, offset: int) -> list[Task]:
        stmt = (
            self._select_task_list_rows_with_tags()
            .where(
                TaskModel.creator_id == user_id,
                self._task_is_not_deleted(),
                TaskModel.due_at < func.now(),
                TaskModel.status == TaskStatus.ACTIVE,
            )
            .order_by(TaskModel.due_at, TaskModel.created_at)
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return self._task_list_rows_to_tasks(result.all())

    @translate_repository_errors
    async def get_task(self, user_id: UUID, task_id: UUID) -> Task:
        stmt = self._select_tasks_with_tags().where(
            TaskModel.creator_id == user_id,
            TaskModel.task_id == task_id,
            self._task_is_not_deleted(),
        )

        result = await self.session.execute(stmt)
        return self._model_to_task(result.scalar_one())

    async def exists_task(self, user_id: UUID, task_id: UUID) -> bool:
        stmt = select(
            select(1)
            .select_from(TaskModel)
            .where(
                TaskModel.creator_id == user_id,
                TaskModel.task_id == task_id,
                self._task_is_not_deleted(),
            )
            .exists()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists_task_including_deleted(self, user_id: UUID, task_id: UUID) -> bool:
        stmt = select(
            select(1)
            .select_from(TaskModel)
            .where(TaskModel.creator_id == user_id, TaskModel.task_id == task_id)
            .exists()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    @translate_repository_errors
    async def add_task(self, user_id: UUID, data: AddTask) -> Task:
        values = {"creator_id": user_id, **self._task_insert_values(data)}
        stmt = insert(TaskModel).values(**values).returning(TaskModel.task_id)

        result = await self.session.execute(stmt)
        task_id = result.scalar_one()
        await self._add_tags_to_task(user_id, task_id, data.tag_ids)
        await self._upsert_task_schedule(user_id, task_id, data.schedule)

        return await self.get_task(user_id, task_id)

    @translate_repository_errors
    async def add_tag_to_task(self, user_id: UUID, task_id: UUID, tag_id: UUID) -> None:
        await self._add_tags_to_task(user_id, task_id, (tag_id,))

    @translate_repository_errors
    async def update_task(self, user_id: UUID, task_id: UUID, data: UpdateTaskData) -> Task:
        values = self._task_update_values(data)
        if values:
            changed_task = (
                self._update_task_stmt(user_id, task_id, values)
                .returning(TaskModel.task_id)
                .cte("changed_task")
            )
        else:
            changed_task = (
                select(TaskModel.task_id)
                .where(
                    TaskModel.creator_id == user_id,
                    TaskModel.task_id == task_id,
                    self._task_is_not_deleted(),
                )
                .cte("changed_task")
            )

        upserted_schedule = None
        if data.schedule is not None:
            await self._raise_if_schedule_overlaps(user_id, task_id, data.schedule)
            schedule_values = {
                "starts_at": data.schedule.starts_at,
                "ends_at": data.schedule.ends_at,
            }
            upserted_schedule = (
                pg_insert(ScheduledTaskModel)
                .from_select(
                    (
                        ScheduledTaskModel.task_id,
                        ScheduledTaskModel.starts_at,
                        ScheduledTaskModel.ends_at,
                    ),
                    select(
                        changed_task.c.task_id,
                        literal(data.schedule.starts_at),
                        literal(data.schedule.ends_at),
                    ),
                )
                .on_conflict_do_update(index_elements=["task_id"], set_=schedule_values)
                .returning(ScheduledTaskModel.task_id)
                .cte("upserted_task_schedule")
            )

        customized_instance = self._customize_recurrence_instance(
            upserted_schedule if upserted_schedule is not None else changed_task,
            cte_name="customized_task_recurrence_instance",
        )
        stmt = select(select(1).select_from(changed_task).exists()).add_cte(customized_instance)
        if upserted_schedule is not None:
            stmt = stmt.add_cte(upserted_schedule)
        await self.session.execute(stmt)
        return await self.get_task(user_id, task_id)

    async def delete_task(self, user_id: UUID, task_id: UUID) -> None:
        stmt = delete(TaskModel).where(
            TaskModel.creator_id == user_id,
            TaskModel.task_id == task_id,
            self._task_is_not_deleted(),
        )

        await self.session.execute(stmt)

    async def delete_tag_from_task(self, user_id: UUID, task_id: UUID, tag_id: UUID) -> None:
        stmt = delete(TaskTagModel).where(
            TaskTagModel.task_id == task_id,
            TaskTagModel.tag_id == tag_id,
            select(1)
            .select_from(TaskModel)
            .where(TaskModel.creator_id == user_id, TaskModel.task_id == TaskTagModel.task_id)
            .where(self._task_is_not_deleted())
            .exists(),
            select(1)
            .select_from(TagModel)
            .where(
                TagModel.creator_id == user_id,
                TagModel.tag_id == TaskTagModel.tag_id,
                self._tag_is_not_deleted(),
            )
            .exists(),
        )

        await self.session.execute(stmt)

    async def _add_tags_to_task(
        self,
        user_id: UUID,
        task_id: UUID,
        tag_ids: tuple[UUID, ...],
    ) -> None:
        unique_tag_ids = set(tag_ids)

        if not unique_tag_ids:
            return

        await self._raise_if_tags_do_not_belong_to_user(user_id, unique_tag_ids)

        stmt = (
            pg_insert(TaskTagModel)
            .values([{"task_id": task_id, "tag_id": tag_id} for tag_id in unique_tag_ids])
            .on_conflict_do_nothing(index_elements=["task_id", "tag_id"])
        )

        await self.session.execute(stmt)

    async def _get_recurrence_conflicts_as_tasks(
        self, user_id: UUID, filters: ListTasksFilters
    ) -> list[Task]:
        if not self._should_include_recurrence_conflicts(filters):
            return []

        stmt = self._select_recurrence_conflict_task_rows(user_id, filters).order_by(
            TaskRecurrenceMaterializationConflictModel.planned_ends_at,
            TaskRecurrenceMaterializationConflictModel.created_at,
        )
        result = await self.session.execute(stmt)
        return [self._row_to_recurrence_conflict_task(row) for row in result.all()]

    @classmethod
    def _select_recurrence_conflict_task_rows(cls, user_id: UUID, filters: ListTasksFilters):
        return (
            select(
                TaskRecurrenceMaterializationConflictModel.conflict_id,
                TaskRecurrenceMaterializationConflictModel.series_id,
                TaskRecurrenceMaterializationConflictModel.planned_starts_at,
                TaskRecurrenceMaterializationConflictModel.planned_ends_at,
                TaskRecurrenceMaterializationConflictModel.reason,
                TaskRecurrenceMaterializationConflictModel.created_at,
                TaskRecurrenceTemplateModel.title,
                TaskRecurrenceTemplateModel.description,
                TaskRecurrenceTemplateModel.priority,
            )
            .select_from(TaskRecurrenceMaterializationConflictModel)
            .join(
                TaskRecurrenceSeriesModel,
                TaskRecurrenceSeriesModel.series_id
                == TaskRecurrenceMaterializationConflictModel.series_id,
            )
            .join(
                TaskRecurrenceTemplateModel,
                TaskRecurrenceTemplateModel.template_id == TaskRecurrenceSeriesModel.template_id,
            )
            .where(
                TaskRecurrenceTemplateModel.creator_id == user_id,
                TaskRecurrenceTemplateModel.deleted_at.is_(None),
                TaskRecurrenceSeriesModel.deleted_at.is_(None),
                TaskRecurrenceMaterializationConflictModel.resolved_at.is_(None),
                *cls._build_recurrence_conflict_filters(filters),
            )
        )

    @staticmethod
    def _should_include_recurrence_conflicts(filters: ListTasksFilters) -> bool:
        return filters.include_recurring and (
            filters.due_from is not None or filters.due_to is not None
        )

    @staticmethod
    def _build_recurrence_conflict_filters(filters: ListTasksFilters):
        conditions = []

        if filters.tag_ids:
            return [false()]
        if filters.statuses and TaskStatus.ACTIVE not in filters.statuses:
            return [false()]
        if filters.priorities:
            conditions.append(TaskRecurrenceTemplateModel.priority.in_(filters.priorities))
        if filters.due_from:
            conditions.append(
                TaskRecurrenceMaterializationConflictModel.planned_ends_at >= filters.due_from
            )
        if filters.due_to:
            conditions.append(
                TaskRecurrenceMaterializationConflictModel.planned_ends_at <= filters.due_to
            )
        if filters.starts_from:
            conditions.append(
                TaskRecurrenceMaterializationConflictModel.planned_starts_at >= filters.starts_from
            )
        if filters.starts_to:
            conditions.append(
                TaskRecurrenceMaterializationConflictModel.planned_starts_at <= filters.starts_to
            )
        if filters.ends_from:
            conditions.append(
                TaskRecurrenceMaterializationConflictModel.planned_ends_at >= filters.ends_from
            )
        if filters.ends_to:
            conditions.append(
                TaskRecurrenceMaterializationConflictModel.planned_ends_at <= filters.ends_to
            )
        if filters.search_text:
            conditions.append(TaskRecurrenceTemplateModel.title.ilike(f"%{filters.search_text}%"))

        return conditions
