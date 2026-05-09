from uuid import UUID

from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.value_objects.tasks import FreeTime, Schedule, Task, TaskStatus
from dto.tasks import AddTask, ListTasksFilters, UpdateTaskData
import exceptions as app_exc


class TaskService:
    """Application service with task operations intended for agent tools/use cases."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def create_task(self, user_id: UUID, data: AddTask) -> Task:
        async with self.uow() as uow:
            return await uow.task.add_task(user_id, data)

    async def get_task(self, user_id: UUID, task_id: UUID) -> Task:
        async with self.uow(read_only=True) as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            return await uow.task.get_task(user_id, task_id)

    async def get_tasks(self, user_id: UUID, filters: ListTasksFilters | None = None) -> list[Task]:
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
        return await self.get_tasks(
            user_id,
            ListTasksFilters(
                statuses=(TaskStatus.ACTIVE,),
                limit=limit,
                offset=offset,
            ),
        )

    async def get_completed_tasks(
        self,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        return await self.get_tasks(
            user_id,
            ListTasksFilters(
                statuses=(TaskStatus.COMPLETED,),
                limit=limit,
                offset=offset,
            ),
        )

    async def get_overdue_tasks(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_overdue_tasks(user_id, limit, offset)

    async def get_free_time(self, user_id: UUID, window: Schedule) -> list[FreeTime]:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_free_time(user_id, window)

    async def update_task(self, user_id: UUID, task_id: UUID, data: UpdateTaskData) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            return await uow.task.update_task(user_id, task_id, data)

    async def complete_task(self, user_id: UUID, task_id: UUID) -> Task:
        return await self.update_task(
            user_id,
            task_id,
            UpdateTaskData(status=TaskStatus.COMPLETED),
        )

    async def reopen_task(self, user_id: UUID, task_id: UUID) -> Task:
        return await self.update_task(
            user_id,
            task_id,
            UpdateTaskData(status=TaskStatus.ACTIVE),
        )

    async def cancel_task(self, user_id: UUID, task_id: UUID) -> Task:
        return await self.update_task(
            user_id,
            task_id,
            UpdateTaskData(status=TaskStatus.CANCELLED),
        )

    async def delete_task(self, user_id: UUID, task_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await uow.task.delete_task(user_id, task_id)

    async def delete_schedule_from_task(self, user_id: UUID, task_id: UUID) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await uow.task.delete_schedule_from_task(user_id, task_id)
            return await uow.task.get_task(user_id, task_id)

    async def add_tag_to_task(self, user_id: UUID, task_id: UUID, tag_id: UUID) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await self._check_if_tag_exists(uow, user_id, tag_id)
            await uow.task.add_tag_to_task(user_id, task_id, tag_id)
            return await uow.task.get_task(user_id, task_id)

    async def delete_tag_from_task(self, user_id: UUID, task_id: UUID, tag_id: UUID) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, user_id, task_id)
            await self._check_if_tag_exists(uow, user_id, tag_id)
            await uow.task.delete_tag_from_task(user_id, task_id, tag_id)
            return await uow.task.get_task(user_id, task_id)

    async def _check_if_task_exists(self, uow, user_id: UUID, task_id: UUID) -> None:
        if not await uow.task.exists_task(user_id, task_id):
            raise app_exc.TaskNotFound

    async def _check_if_tag_exists(self, uow, user_id: UUID, tag_id: UUID) -> None:
        if not await uow.tag.exists_tag(user_id, tag_id):
            raise app_exc.TagNotFound
