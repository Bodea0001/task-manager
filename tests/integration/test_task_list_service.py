from datetime import datetime, timedelta

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
    assert sut.conflicts == []
    assert task_ids_with_test_prefix(sut) == {first.task_id, second.task_id}


@pytest.mark.asyncio
async def test_get_tasks_returns_task_list_contract(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="task-list-contract")

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=task.due_at - timedelta(minutes=1),
            due_to=task.due_at + timedelta(minutes=1),
        ),
    )
    count = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=task.due_at - timedelta(minutes=1),
            due_to=task.due_at + timedelta(minutes=1),
        ),
    )

    # Assert
    assert [item.task_id for item in sut.tasks] == [task.task_id]
    assert sut.conflicts == []
    assert count == len(sut.tasks)


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
    assert first.task_id not in {task.task_id for task in sut.tasks}


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
    sut = await task_service.get_free_time(TEST_USER_ID, [window])

    # Assert
    assert sut == [FreeTime(starts_at=window.starts_at, ends_at=window.ends_at)]


@pytest.mark.asyncio
async def test_user_can_view_free_time_for_multiple_windows(task_service: TaskService) -> None:
    # Arrange
    await create_task(
        task_service,
        title="free-time-multiple-first-busy",
        starts_at=datetime(2099, 8, 1, 10, 0),
        ends_at=datetime(2099, 8, 1, 11, 0),
    )
    await create_task(
        task_service,
        title="free-time-multiple-second-busy",
        starts_at=datetime(2099, 8, 2, 14, 0),
        ends_at=datetime(2099, 8, 2, 15, 0),
    )

    # Act
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        [
            Schedule(
                starts_at=datetime(2099, 8, 1, 9, 0),
                ends_at=datetime(2099, 8, 1, 12, 0),
            ),
            Schedule(
                starts_at=datetime(2099, 8, 2, 13, 0),
                ends_at=datetime(2099, 8, 2, 16, 0),
            ),
        ],
    )

    # Assert
    assert sut == [
        FreeTime(
            starts_at=datetime(2099, 8, 1, 9, 0),
            ends_at=datetime(2099, 8, 1, 10, 0),
        ),
        FreeTime(
            starts_at=datetime(2099, 8, 1, 11, 0),
            ends_at=datetime(2099, 8, 1, 12, 0),
        ),
        FreeTime(
            starts_at=datetime(2099, 8, 2, 13, 0),
            ends_at=datetime(2099, 8, 2, 14, 0),
        ),
        FreeTime(
            starts_at=datetime(2099, 8, 2, 15, 0),
            ends_at=datetime(2099, 8, 2, 16, 0),
        ),
    ]


@pytest.mark.asyncio
async def test_user_can_view_free_time_from_schedule_iterable(
    task_service: TaskService,
) -> None:
    # Arrange
    window = Schedule(
        starts_at=datetime(2099, 8, 6, 9, 0),
        ends_at=datetime(2099, 8, 6, 18, 0),
    )

    # Act
    sut = await task_service.get_free_time(TEST_USER_ID, (item for item in [window]))

    # Assert
    assert sut == [FreeTime(starts_at=window.starts_at, ends_at=window.ends_at)]


@pytest.mark.asyncio
async def test_free_time_validates_each_window_in_iterable(
    task_service: TaskService,
) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="ends_at cannot be earlier than starts_at"):
        await task_service.get_free_time(
            TEST_USER_ID,
            [
                Schedule(
                    starts_at=datetime(2099, 8, 7, 9, 0),
                    ends_at=datetime(2099, 8, 7, 18, 0),
                ),
                Schedule(
                    starts_at=datetime(2099, 8, 8, 18, 0),
                    ends_at=datetime(2099, 8, 8, 9, 0),
                ),
            ],
        )


@pytest.mark.asyncio
async def test_free_time_handles_free_and_partially_busy_windows(
    task_service: TaskService,
) -> None:
    # Arrange
    await create_task(
        task_service,
        title="free-time-mixed-busy",
        starts_at=datetime(2099, 8, 10, 11, 0),
        ends_at=datetime(2099, 8, 10, 12, 0),
    )

    free_window = Schedule(
        starts_at=datetime(2099, 8, 9, 9, 0),
        ends_at=datetime(2099, 8, 9, 18, 0),
    )
    partially_busy_window = Schedule(
        starts_at=datetime(2099, 8, 10, 9, 0),
        ends_at=datetime(2099, 8, 10, 13, 0),
    )

    # Act
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        [free_window, partially_busy_window],
    )

    # Assert
    assert sut == [
        FreeTime(starts_at=free_window.starts_at, ends_at=free_window.ends_at),
        FreeTime(
            starts_at=datetime(2099, 8, 10, 9, 0),
            ends_at=datetime(2099, 8, 10, 11, 0),
        ),
        FreeTime(
            starts_at=datetime(2099, 8, 10, 12, 0),
            ends_at=datetime(2099, 8, 10, 13, 0),
        ),
    ]


@pytest.mark.asyncio
async def test_free_time_requires_at_least_one_window(
    task_service: TaskService,
) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="at least one schedule window is required"):
        await task_service.get_free_time(TEST_USER_ID, [])


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
async def test_user_can_find_nearest_free_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    search_from = datetime(2099, 8, 8, 9, 0)
    await create_task(
        task_service,
        title="nearest-free-busy",
        starts_at=datetime(2099, 8, 8, 10, 0),
        ends_at=datetime(2099, 8, 8, 11, 0),
    )

    # Act
    sut = await task_service.find_nearest_free_schedule(
        TEST_USER_ID,
        duration=timedelta(minutes=30),
        excluded_windows=(
            Schedule(
                starts_at=datetime(2099, 8, 8, 9, 0),
                ends_at=datetime(2099, 8, 8, 10, 0),
            ),
        ),
        search_from=search_from,
    )

    # Assert
    assert sut == Schedule(
        starts_at=datetime(2099, 8, 8, 11, 0),
        ends_at=datetime(2099, 8, 8, 11, 30),
    )


@pytest.mark.asyncio
async def test_nearest_free_schedule_uses_gap_before_next_busy_window(
    task_service: TaskService,
) -> None:
    # Arrange
    search_from = datetime(2099, 8, 9, 9, 0)
    await create_task(
        task_service,
        title="nearest-free-next-busy",
        starts_at=datetime(2099, 8, 9, 12, 0),
        ends_at=datetime(2099, 8, 9, 13, 0),
    )

    # Act
    sut = await task_service.find_nearest_free_schedule(
        TEST_USER_ID,
        duration=timedelta(minutes=45),
        excluded_windows=(
            Schedule(
                starts_at=datetime(2099, 8, 9, 9, 0),
                ends_at=datetime(2099, 8, 9, 10, 30),
            ),
        ),
        search_from=search_from,
    )

    # Assert
    assert sut == Schedule(
        starts_at=datetime(2099, 8, 9, 10, 30),
        ends_at=datetime(2099, 8, 9, 11, 15),
    )


@pytest.mark.asyncio
async def test_nearest_free_schedule_skips_candidates_inside_overlapping_busy_windows(
    task_service: TaskService,
) -> None:
    # Arrange
    search_from = datetime(2099, 8, 10, 10, 0)
    await create_task(
        task_service,
        title="nearest-free-overlap-busy",
        starts_at=search_from,
        ends_at=datetime(2099, 8, 10, 12, 0),
    )

    # Act
    sut = await task_service.find_nearest_free_schedule(
        TEST_USER_ID,
        duration=timedelta(minutes=30),
        excluded_windows=(
            Schedule(
                starts_at=datetime(2099, 8, 10, 11, 0),
                ends_at=datetime(2099, 8, 10, 13, 0),
            ),
        ),
        search_from=search_from,
    )

    # Assert
    assert sut == Schedule(
        starts_at=datetime(2099, 8, 10, 13, 0),
        ends_at=datetime(2099, 8, 10, 13, 30),
    )


@pytest.mark.asyncio
async def test_nearest_free_schedule_requires_positive_duration(
    task_service: TaskService,
) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="duration must be positive"):
        await task_service.find_nearest_free_schedule(
            TEST_USER_ID,
            duration=timedelta(0),
            search_from=datetime(2099, 8, 10, 9, 0),
        )


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
        [
            Schedule(
                starts_at=datetime(2099, 8, 2, 9, 0),
                ends_at=datetime(2099, 8, 2, 15, 0),
            )
        ],
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
        [
            Schedule(
                starts_at=datetime(2099, 8, 3, 9, 0),
                ends_at=datetime(2099, 8, 3, 18, 0),
            )
        ],
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
        [
            Schedule(
                starts_at=datetime(2099, 8, 4, 9, 0),
                ends_at=datetime(2099, 8, 4, 18, 0),
            )
        ],
    )

    # Assert
    assert sut == []
