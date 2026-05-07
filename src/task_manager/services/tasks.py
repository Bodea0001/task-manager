from uuid import UUID

from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.value_objects.tasks import Task, TaskStatus
from dto.tasks import AddTask, ListTasksFilters, UpdateTaskData
import exceptions as app_exc


class TaskService:
    """Application service with task operations intended for agent tools/use cases."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def create_task(self, data: AddTask) -> Task:
        async with self.uow() as uow:
            return await uow.task.add_task(data)

    async def get_task(self, task_id: UUID) -> Task:
        async with self.uow(read_only=True) as uow:
            await self._check_if_task_exists(uow, task_id)
            return await uow.task.get_task(task_id)

    async def get_tasks(self, filters: ListTasksFilters | None = None) -> list[Task]:
        if filters is None:
            filters = ListTasksFilters()

        async with self.uow(read_only=True) as uow:
            return await uow.task.get_tasks(filters)

    async def count_tasks(self, filters: ListTasksFilters | None = None) -> int:
        if filters is None:
            filters = ListTasksFilters()

        async with self.uow(read_only=True) as uow:
            return await uow.task.count_tasks(filters)

    async def get_active_tasks(self, limit: int = 100, offset: int = 0) -> list[Task]:
        return await self.get_tasks(
            ListTasksFilters(
                statuses=(TaskStatus.ACTIVE,),
                limit=limit,
                offset=offset,
            )
        )

    async def get_completed_tasks(self, limit: int = 100, offset: int = 0) -> list[Task]:
        return await self.get_tasks(
            ListTasksFilters(
                statuses=(TaskStatus.COMPLETED,),
                limit=limit,
                offset=offset,
            )
        )

    async def get_overdue_tasks(self, limit: int = 100, offset: int = 0) -> list[Task]:
        async with self.uow(read_only=True) as uow:
            return await uow.task.get_overdue_tasks(limit, offset)

    async def update_task(self, task_id: UUID, data: UpdateTaskData) -> Task:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, task_id)
            return await uow.task.update_task(task_id, data)

    async def complete_task(self, task_id: UUID) -> Task:
        return await self.update_task(
            task_id,
            UpdateTaskData(status=TaskStatus.COMPLETED),
        )

    async def reopen_task(self, task_id: UUID) -> Task:
        return await self.update_task(
            task_id,
            UpdateTaskData(status=TaskStatus.ACTIVE),
        )

    async def cancel_task(self, task_id: UUID) -> Task:
        return await self.update_task(
            task_id,
            UpdateTaskData(status=TaskStatus.CANCELLED),
        )

    async def delete_task(self, task_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_task_exists(uow, task_id)
            await uow.task.delete_task(task_id)

    async def _check_if_task_exists(self, uow, task_id: UUID) -> None:
        if not await uow.task.exists_task(task_id):
            raise app_exc.TaskNotFound
