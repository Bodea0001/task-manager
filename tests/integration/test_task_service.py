from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from constants import TEST_TITLE_PREFIX
from domain.value_objects.tasks import Task, TaskStatus
from dto.tasks import AddTask, ListTasksFilters, UpdateTaskData
from exceptions import TaskNotFound, WrongTaskDeadline
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_create_a_task(service: TaskService) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act
    sut = await service.create_task(
        AddTask(
            title=f"{TEST_TITLE_PREFIX}create",
            description="Initial description",
            starts_at=starts_at,
            ends_at=ends_at,
        )
    )

    # Assert
    assert sut.task_id is not None
    assert sut.title == f"{TEST_TITLE_PREFIX}create"
    assert sut.description == "Initial description"
    assert sut.status == TaskStatus.ACTIVE
    assert sut.starts_at == starts_at
    assert sut.ends_at == ends_at


@pytest.mark.asyncio
async def test_user_can_open_an_existing_task(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="open")

    # Act
    sut = await service.get_task(task.task_id)

    # Assert
    assert sut == task


@pytest.mark.asyncio
async def test_user_can_update_task_details(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="update")
    new_ends_at = task.ends_at + timedelta(hours=2)

    # Act
    sut = await service.update_task(
        task.task_id,
        UpdateTaskData(
            title=f"{TEST_TITLE_PREFIX}updated",
            description="Updated description",
            ends_at=new_ends_at,
        ),
    )

    # Assert
    assert sut.task_id == task.task_id
    assert sut.title == f"{TEST_TITLE_PREFIX}updated"
    assert sut.description == "Updated description"
    assert sut.ends_at == new_ends_at


@pytest.mark.asyncio
async def test_user_can_complete_a_task(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="complete")

    # Act
    sut = await service.complete_task(task.task_id)

    # Assert
    assert sut.status == TaskStatus.COMPLETED
    assert sut.completed_at is not None


@pytest.mark.asyncio
async def test_user_can_reopen_a_completed_task(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="reopen", status=TaskStatus.COMPLETED)

    # Act
    sut = await service.reopen_task(task.task_id)

    # Assert
    assert sut.status == TaskStatus.ACTIVE
    assert sut.completed_at is None


@pytest.mark.asyncio
async def test_user_can_cancel_a_task(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="cancel")

    # Act
    sut = await service.cancel_task(task.task_id)

    # Assert
    assert sut.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_user_can_delete_a_task(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="delete")

    # Act
    await service.delete_task(task.task_id)

    # Assert
    with pytest.raises(TaskNotFound):
        await service.get_task(task.task_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ("get_task", "complete_task", "reopen_task", "cancel_task", "delete_task"),
)
async def test_user_cannot_act_on_missing_task(service: TaskService, action: str) -> None:
    # Arrange
    task_id = uuid4()

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await getattr(service, action)(task_id)


@pytest.mark.asyncio
async def test_user_cannot_update_a_missing_task(service: TaskService) -> None:
    # Arrange
    task_id = uuid4()

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await service.update_task(task_id, UpdateTaskData(title=f"{TEST_TITLE_PREFIX}updated"))


@pytest.mark.asyncio
async def test_user_can_view_active_tasks(service: TaskService) -> None:
    # Arrange
    active = await create_task(service, title="active")
    await create_task(service, title="completed", status=TaskStatus.COMPLETED)

    # Act
    sut = await service.get_active_tasks(limit=1000)

    # Assert
    assert active.task_id in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_view_completed_tasks(service: TaskService) -> None:
    # Arrange
    await create_task(service, title="active")
    completed = await create_task(service, title="completed", status=TaskStatus.COMPLETED)

    # Act
    sut = await service.get_completed_tasks(limit=1000)

    # Assert
    assert completed.task_id in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_view_tasks_with_default_filters(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="default-list")

    # Act
    sut = await service.get_tasks()

    # Assert
    assert task.task_id in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_count_tasks_with_default_filters(service: TaskService) -> None:
    # Arrange
    await create_task(service, title="default-count")

    # Act
    sut = await service.count_tasks()

    # Assert
    assert sut >= 1


@pytest.mark.asyncio
async def test_user_can_view_overdue_tasks(service: TaskService) -> None:
    # Arrange
    overdue = await create_task(
        service,
        title="overdue",
        starts_at=datetime(2001, 1, 1, 10, 0),
    )
    await create_task(service, title="future", starts_at=datetime(2099, 6, 1, 10, 0))

    # Act
    sut = await service.get_overdue_tasks(limit=1000)

    # Assert
    assert overdue.task_id in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_start_and_end_windows(service: TaskService) -> None:
    # Arrange
    matching = await create_task(
        service, title="window-match", starts_at=datetime(2099, 8, 1, 10, 0)
    )
    too_early = await create_task(
        service, title="window-early", starts_at=datetime(2099, 7, 1, 10, 0)
    )
    too_late = await create_task(
        service, title="window-late", starts_at=datetime(2099, 9, 1, 10, 0)
    )

    # Act
    sut = await service.get_tasks(
        ListTasksFilters(
            starts_from=datetime(2099, 8, 1, 0, 0),
            starts_to=datetime(2099, 8, 1, 23, 59),
            ends_from=datetime(2099, 8, 1, 10, 30),
            ends_to=datetime(2099, 8, 1, 11, 30),
            limit=1000,
        )
    )

    # Assert
    ids = task_ids(sut)
    assert matching.task_id in ids
    assert too_early.task_id not in ids
    assert too_late.task_id not in ids


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_filter(service: TaskService) -> None:
    # Arrange
    await create_task(service, title="counted", starts_at=datetime(2099, 6, 1, 10, 0))
    await create_task(service, title="not-counted", starts_at=datetime(2099, 7, 1, 10, 0))

    # Act
    sut = await service.count_tasks(
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE,),
            starts_from=datetime(2099, 6, 1),
            starts_to=datetime(2099, 6, 2),
        )
    )

    # Assert
    assert sut == 1


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_end_filter(service: TaskService) -> None:
    # Arrange
    await create_task(service, title="end-counted", starts_at=datetime(2099, 10, 1, 10, 0))
    await create_task(service, title="end-not-counted", starts_at=datetime(2099, 11, 1, 10, 0))

    # Act
    sut = await service.count_tasks(
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE,),
            ends_from=datetime(2099, 10, 1, 10, 30),
            ends_to=datetime(2099, 10, 1, 11, 30),
        )
    )

    # Assert
    assert sut == 1


@pytest.mark.asyncio
async def test_user_cannot_update_task_with_wrong_deadline(service: TaskService) -> None:
    # Arrange
    task = await create_task(service, title="wrong-update")

    # Act / Assert
    with pytest.raises(WrongTaskDeadline):
        await service.update_task(
            task.task_id,
            UpdateTaskData(ends_at=task.starts_at - timedelta(minutes=1)),
        )


async def create_task(
    service: TaskService,
    *,
    title: str,
    starts_at: datetime | None = None,
    status: TaskStatus = TaskStatus.ACTIVE,
) -> Task:
    if starts_at is None:
        starts_at = datetime(2099, 5, 5, 10, 0)

    return await service.create_task(
        AddTask(
            title=f"{TEST_TITLE_PREFIX}{title}",
            description=f"{title} description",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=status,
        )
    )


def task_ids(tasks: list[Task]) -> set:
    return {task.task_id for task in tasks}
