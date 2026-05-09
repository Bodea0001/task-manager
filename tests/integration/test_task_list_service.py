from datetime import datetime

import pytest

from helpers import create_task, task_ids, task_ids_with_test_prefix

from constants import TEST_TITLE_PREFIX, TEST_USER_ID
from dto.tasks import AddTask, ListTasksFilters
from domain.value_objects.tasks import FreeTime, Schedule, TaskStatus
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_view_active_tasks(task_service: TaskService) -> None:
    # Arrange
    first_active = await create_task(task_service, title="active-first")
    second_active = await create_task(task_service, title="active-second")
    await create_task(task_service, title="completed", status=TaskStatus.COMPLETED)

    # Act
    sut = await task_service.get_active_tasks(TEST_USER_ID, limit=1000)

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
    sut = await task_service.get_completed_tasks(TEST_USER_ID, limit=1000)

    # Assert
    assert task_ids_with_test_prefix(sut) == {first_completed.task_id, second_completed.task_id}


@pytest.mark.asyncio
async def test_user_can_view_tasks_with_default_filters(task_service: TaskService) -> None:
    # Arrange
    first = await create_task(task_service, title="default-list-first")
    second = await create_task(task_service, title="default-list-second")

    # Act
    sut = await task_service.get_tasks(TEST_USER_ID)

    # Assert
    assert task_ids_with_test_prefix(sut) == {first.task_id, second.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_with_default_filters(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="default-count")

    # Act
    sut = await task_service.count_tasks(TEST_USER_ID)

    # Assert
    assert sut >= 1


@pytest.mark.asyncio
async def test_user_can_paginate_tasks_ordered_by_due_date(task_service: TaskService) -> None:
    # Arrange
    first = await create_task(
        task_service,
        title="due-page-first",
        due_at=datetime(2099, 7, 1, 10, 0),
    )
    second = await create_task(
        task_service,
        title="due-page-second",
        due_at=datetime(2099, 7, 2, 10, 0),
    )
    await create_task(
        task_service,
        title="due-page-third",
        due_at=datetime(2099, 7, 3, 10, 0),
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 7, 1),
            due_to=datetime(2099, 7, 4),
            limit=1,
            offset=1,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {second.task_id}
    assert first.task_id not in {task.task_id for task in sut}


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
    sut = await task_service.get_overdue_tasks(TEST_USER_ID, limit=1000)

    # Assert
    assert task_ids_with_test_prefix(sut) == {first_overdue.task_id, second_overdue.task_id}


@pytest.mark.asyncio
async def test_overdue_tasks_are_selected_by_due_date(task_service: TaskService) -> None:
    # Arrange
    overdue = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}overdue-by-due",
            due_at=datetime(2001, 1, 1, 9, 0),
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )
    await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}not-overdue-by-due",
            due_at=datetime(2099, 1, 1, 9, 0),
            schedule=Schedule(
                starts_at=datetime(2001, 1, 1, 10, 0),
                ends_at=datetime(2001, 1, 1, 11, 0),
            ),
        ),
    )

    # Act
    sut = await task_service.get_overdue_tasks(TEST_USER_ID, limit=1000)

    # Assert
    assert task_ids_with_test_prefix(sut) == {overdue.task_id}


@pytest.mark.asyncio
async def test_user_can_view_free_time_for_empty_schedule(task_service: TaskService) -> None:
    # Arrange
    window = Schedule(
        starts_at=datetime(2099, 8, 1, 9, 0),
        ends_at=datetime(2099, 8, 1, 18, 0),
    )

    # Act
    sut = await task_service.get_free_time(TEST_USER_ID, window)

    # Assert
    assert sut == [FreeTime(starts_at=window.starts_at, ends_at=window.ends_at)]


@pytest.mark.asyncio
async def test_user_can_check_available_schedule_window(task_service: TaskService) -> None:
    # Arrange
    window = Schedule(
        starts_at=datetime(2099, 8, 5, 10, 0),
        ends_at=datetime(2099, 8, 5, 11, 0),
    )
    await create_task(
        task_service,
        title="availability-before",
        starts_at=datetime(2099, 8, 5, 9, 0),
        ends_at=window.starts_at,
    )
    await create_task(
        task_service,
        title="availability-after",
        starts_at=window.ends_at,
        ends_at=datetime(2099, 8, 5, 12, 0),
    )

    # Act
    sut = await task_service.check_schedule_availability(TEST_USER_ID, window)

    # Assert
    assert sut.can_add_task
    assert sut.blocking_tasks == []


@pytest.mark.asyncio
async def test_schedule_availability_returns_blocking_tasks(task_service: TaskService) -> None:
    # Arrange
    first_blocking = await create_task(
        task_service,
        title="availability-first-blocking",
        starts_at=datetime(2099, 8, 6, 9, 30),
        ends_at=datetime(2099, 8, 6, 10, 30),
    )
    second_blocking = await create_task(
        task_service,
        title="availability-second-blocking",
        starts_at=datetime(2099, 8, 6, 10, 45),
        ends_at=datetime(2099, 8, 6, 11, 30),
    )
    await create_task(
        task_service,
        title="availability-touching",
        starts_at=datetime(2099, 8, 6, 12, 0),
        ends_at=datetime(2099, 8, 6, 13, 0),
    )

    # Act
    sut = await task_service.check_schedule_availability(
        TEST_USER_ID,
        Schedule(
            starts_at=datetime(2099, 8, 6, 10, 0),
            ends_at=datetime(2099, 8, 6, 12, 0),
        ),
    )

    # Assert
    assert not sut.can_add_task
    assert task_ids(sut.blocking_tasks) == {first_blocking.task_id, second_blocking.task_id}
    assert [task.task_id for task in sut.blocking_tasks] == [
        first_blocking.task_id,
        second_blocking.task_id,
    ]


@pytest.mark.asyncio
async def test_schedule_availability_ignores_unscheduled_tasks(task_service: TaskService) -> None:
    # Arrange
    window = Schedule(
        starts_at=datetime(2099, 8, 7, 10, 0),
        ends_at=datetime(2099, 8, 7, 11, 0),
    )
    await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}availability-unscheduled",
            due_at=window.starts_at,
            schedule=None,
        ),
    )

    # Act
    sut = await task_service.check_schedule_availability(TEST_USER_ID, window)

    # Assert
    assert sut.can_add_task
    assert sut.blocking_tasks == []


@pytest.mark.asyncio
async def test_user_can_view_sorted_free_time_between_scheduled_tasks(
    task_service: TaskService,
) -> None:
    # Arrange
    await create_task(
        task_service,
        title="free-time-first-busy",
        starts_at=datetime(2099, 8, 2, 10, 0),
        ends_at=datetime(2099, 8, 2, 11, 0),
    )
    await create_task(
        task_service,
        title="free-time-second-busy",
        starts_at=datetime(2099, 8, 2, 13, 0),
        ends_at=datetime(2099, 8, 2, 14, 0),
    )

    # Act
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        Schedule(
            starts_at=datetime(2099, 8, 2, 9, 0),
            ends_at=datetime(2099, 8, 2, 15, 0),
        ),
    )

    # Assert
    assert sut == [
        FreeTime(
            starts_at=datetime(2099, 8, 2, 9, 0),
            ends_at=datetime(2099, 8, 2, 10, 0),
        ),
        FreeTime(
            starts_at=datetime(2099, 8, 2, 11, 0),
            ends_at=datetime(2099, 8, 2, 13, 0),
        ),
        FreeTime(
            starts_at=datetime(2099, 8, 2, 14, 0),
            ends_at=datetime(2099, 8, 2, 15, 0),
        ),
    ]


@pytest.mark.asyncio
async def test_free_time_view_clips_scheduled_tasks_to_window(
    task_service: TaskService,
) -> None:
    # Arrange
    await create_task(
        task_service,
        title="free-time-overlaps-start",
        starts_at=datetime(2099, 8, 3, 8, 0),
        ends_at=datetime(2099, 8, 3, 10, 0),
    )
    await create_task(
        task_service,
        title="free-time-overlaps-end",
        starts_at=datetime(2099, 8, 3, 16, 0),
        ends_at=datetime(2099, 8, 3, 19, 0),
    )

    # Act
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        Schedule(
            starts_at=datetime(2099, 8, 3, 9, 0),
            ends_at=datetime(2099, 8, 3, 18, 0),
        ),
    )

    # Assert
    assert sut == [
        FreeTime(
            starts_at=datetime(2099, 8, 3, 10, 0),
            ends_at=datetime(2099, 8, 3, 16, 0),
        )
    ]


@pytest.mark.asyncio
async def test_free_time_view_returns_empty_list_when_window_is_fully_busy(
    task_service: TaskService,
) -> None:
    # Arrange
    await create_task(
        task_service,
        title="free-time-fully-busy",
        starts_at=datetime(2099, 8, 4, 9, 0),
        ends_at=datetime(2099, 8, 4, 18, 0),
    )

    # Act
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        Schedule(
            starts_at=datetime(2099, 8, 4, 9, 0),
            ends_at=datetime(2099, 8, 4, 18, 0),
        ),
    )

    # Assert
    assert sut == []
