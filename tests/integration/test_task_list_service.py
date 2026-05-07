from datetime import datetime

import pytest

from helpers import create_task, task_ids_with_test_prefix

from domain.value_objects.tasks import TaskStatus
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_view_active_tasks(task_service: TaskService) -> None:
    # Arrange
    first_active = await create_task(task_service, title="active-first")
    second_active = await create_task(task_service, title="active-second")
    await create_task(task_service, title="completed", status=TaskStatus.COMPLETED)

    # Act
    sut = await task_service.get_active_tasks(limit=1000)

    # Assert
    assert task_ids_with_test_prefix(sut) == {first_active.task_id, second_active.task_id}


@pytest.mark.asyncio
async def test_user_can_view_completed_tasks(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="active")
    first_completed = await create_task(
        task_service, title="completed-first", status=TaskStatus.COMPLETED
    )
    second_completed = await create_task(
        task_service, title="completed-second", status=TaskStatus.COMPLETED
    )

    # Act
    sut = await task_service.get_completed_tasks(limit=1000)

    # Assert
    assert task_ids_with_test_prefix(sut) == {first_completed.task_id, second_completed.task_id}


@pytest.mark.asyncio
async def test_user_can_view_tasks_with_default_filters(task_service: TaskService) -> None:
    # Arrange
    first = await create_task(task_service, title="default-list-first")
    second = await create_task(task_service, title="default-list-second")

    # Act
    sut = await task_service.get_tasks()

    # Assert
    assert task_ids_with_test_prefix(sut) == {first.task_id, second.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_with_default_filters(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="default-count")

    # Act
    sut = await task_service.count_tasks()

    # Assert
    assert sut >= 1


@pytest.mark.asyncio
async def test_user_can_view_overdue_tasks(task_service: TaskService) -> None:
    # Arrange
    first_overdue = await create_task(
        task_service,
        title="overdue-first",
        starts_at=datetime(2001, 1, 1, 10, 0),
    )
    second_overdue = await create_task(
        task_service,
        title="overdue-second",
        starts_at=datetime(2001, 1, 2, 10, 0),
    )
    await create_task(task_service, title="future", starts_at=datetime(2099, 6, 1, 10, 0))

    # Act
    sut = await task_service.get_overdue_tasks(limit=1000)

    # Assert
    assert task_ids_with_test_prefix(sut) == {first_overdue.task_id, second_overdue.task_id}
