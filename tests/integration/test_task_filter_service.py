from datetime import datetime

import pytest

from helpers import create_tag, create_task, task_ids, task_ids_with_test_prefix

from constants import TEST_TITLE_PREFIX, TEST_USER_ID
from dto.tasks import AddTask, ListTasksFilters
from domain.value_objects.tasks import TaskPriority, TaskStatus
from services.tags import TagService
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_start_and_end_windows(task_service: TaskService) -> None:
    # Arrange
    matching = await create_task(
        task_service, title="window-match", starts_at=datetime(2099, 8, 1, 10, 0)
    )
    too_early = await create_task(
        task_service, title="window-early", starts_at=datetime(2099, 7, 1, 10, 0)
    )
    too_late = await create_task(
        task_service, title="window-late", starts_at=datetime(2099, 9, 1, 10, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 8, 1, 0, 0),
            starts_to=datetime(2099, 8, 1, 23, 59),
            ends_from=datetime(2099, 8, 1, 10, 30),
            ends_to=datetime(2099, 8, 1, 11, 30),
            limit=1000,
        ),
    )

    # Assert
    ids = task_ids(sut)
    assert matching.task_id in ids
    assert too_early.task_id not in ids
    assert too_late.task_id not in ids


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_start_from_and_end_to(
    task_service: TaskService,
) -> None:
    # Arrange
    matching = await create_task(
        task_service, title="start-from-end-to-match", starts_at=datetime(2099, 8, 2, 10, 0)
    )
    await create_task(
        task_service, title="start-from-end-to-before", starts_at=datetime(2099, 8, 1, 10, 0)
    )
    await create_task(
        task_service, title="start-from-end-to-after-end", starts_at=datetime(2099, 8, 2, 11, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 8, 2, 0, 0),
            ends_to=datetime(2099, 8, 2, 11, 30),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_start_to_and_end_from(
    task_service: TaskService,
) -> None:
    # Arrange
    matching = await create_task(
        task_service, title="start-to-end-from-match", starts_at=datetime(2099, 8, 3, 10, 0)
    )
    await create_task(
        task_service, title="start-to-end-from-before-end", starts_at=datetime(2099, 8, 3, 8, 0)
    )
    await create_task(
        task_service, title="start-to-end-from-after-start", starts_at=datetime(2099, 8, 4, 10, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_to=datetime(2099, 8, 3, 10, 30),
            ends_from=datetime(2099, 8, 3, 10, 30),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_inclusive_time_boundaries(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 8, 5, 10, 0)
    ends_at = datetime(2099, 8, 5, 12, 0)
    matching = await create_task(
        task_service,
        title="time-boundary-match",
        starts_at=starts_at,
        ends_at=ends_at,
    )
    await create_task(
        task_service,
        title="time-boundary-before-start",
        starts_at=datetime(2099, 8, 5, 8, 0),
        ends_at=datetime(2099, 8, 5, 9, 0),
    )
    await create_task(
        task_service,
        title="time-boundary-after-end",
        starts_at=datetime(2099, 8, 5, 13, 0),
        ends_at=datetime(2099, 8, 5, 14, 0),
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            starts_to=starts_at,
            ends_from=ends_at,
            ends_to=ends_at,
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_multiple_statuses(task_service: TaskService) -> None:
    # Arrange
    active = await create_task(task_service, title="status-active")
    completed = await create_task(
        task_service, title="status-completed", status=TaskStatus.COMPLETED
    )
    await create_task(task_service, title="status-cancelled", status=TaskStatus.CANCELLED)

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE, TaskStatus.COMPLETED),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {active.task_id, completed.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_multiple_priorities(task_service: TaskService) -> None:
    # Arrange
    low = await create_task(task_service, title="priority-low", priority=TaskPriority.LOW)
    high = await create_task(task_service, title="priority-high", priority=TaskPriority.HIGH)
    urgent = await create_task(
        task_service,
        title="priority-urgent",
        priority=TaskPriority.URGENT,
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            priorities=(TaskPriority.HIGH, TaskPriority.URGENT),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {high.task_id, urgent.task_id}
    assert low.task_id not in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_tag(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    matching = await create_task(task_service, title="tag-filter-match")
    other = await create_task(task_service, title="tag-filter-other")
    without_tag = await create_task(task_service, title="tag-filter-without")
    tag = await create_tag(tag_service, name="task-filter")
    other_tag = await create_tag(tag_service, name="task-filter-other")
    await task_service.add_tag_to_task(TEST_USER_ID, matching.task_id, tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, other.task_id, other_tag.tag_id)

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            tag_ids=(tag.tag_id,),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}
    assert without_tag.task_id not in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_any_of_multiple_tags(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    first = await create_task(task_service, title="multi-tag-filter-first")
    second = await create_task(task_service, title="multi-tag-filter-second")
    await create_task(task_service, title="multi-tag-filter-other")
    first_tag = await create_tag(tag_service, name="multi-task-filter-first")
    second_tag = await create_tag(tag_service, name="multi-task-filter-second")
    await task_service.add_tag_to_task(TEST_USER_ID, first.task_id, first_tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, second.task_id, second_tag.tag_id)

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            tag_ids=(first_tag.tag_id, second_tag.tag_id),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {first.task_id, second.task_id}


@pytest.mark.asyncio
async def test_multiple_tag_filter_does_not_duplicate_matching_tasks(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    matching = await create_task(task_service, title="multi-tag-no-duplicate")
    other = await create_task(task_service, title="multi-tag-no-duplicate-other")
    first_tag = await create_tag(tag_service, name="multi-task-no-duplicate-first")
    second_tag = await create_tag(tag_service, name="multi-task-no-duplicate-second")
    await task_service.add_tag_to_task(TEST_USER_ID, matching.task_id, first_tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, matching.task_id, second_tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, other.task_id, second_tag.tag_id)

    # Act
    filters = ListTasksFilters(tag_ids=(first_tag.tag_id, second_tag.tag_id), limit=1000)
    tasks = await task_service.get_tasks(TEST_USER_ID, filters)
    count = await task_service.count_tasks(TEST_USER_ID, filters)

    # Assert
    assert [task.task_id for task in tasks if task.task_id == matching.task_id] == [
        matching.task_id
    ]
    assert task_ids_with_test_prefix(tasks) == {matching.task_id, other.task_id}
    assert count == 2


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_due_window(task_service: TaskService) -> None:
    # Arrange
    matching = await create_task(
        task_service,
        title="due-window-match",
        due_at=datetime(2099, 8, 2, 12, 0),
    )
    await create_task(
        task_service,
        title="due-window-before",
        due_at=datetime(2099, 8, 1, 12, 0),
    )
    await create_task(
        task_service,
        title="due-window-after",
        due_at=datetime(2099, 8, 3, 12, 0),
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 8, 2, 0, 0),
            due_to=datetime(2099, 8, 2, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_empty_search_text_is_ignored(task_service: TaskService) -> None:
    # Arrange
    first = await create_task(
        task_service,
        title="empty-search-first",
        due_at=datetime(2099, 8, 4, 12, 0),
    )
    second = await create_task(
        task_service,
        title="empty-search-second",
        due_at=datetime(2099, 8, 4, 13, 0),
    )
    await create_task(
        task_service,
        title="empty-search-outside-window",
        due_at=datetime(2099, 8, 5, 12, 0),
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            search_text="",
            due_from=datetime(2099, 8, 4, 0, 0),
            due_to=datetime(2099, 8, 4, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {first.task_id, second.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_due_window(task_service: TaskService) -> None:
    # Arrange
    await create_task(
        task_service,
        title="due-count-match",
        due_at=datetime(2099, 8, 2, 12, 0),
    )
    await create_task(
        task_service,
        title="due-count-other",
        due_at=datetime(2099, 8, 3, 12, 0),
    )

    # Act
    sut = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 8, 2, 0, 0),
            due_to=datetime(2099, 8, 2, 23, 59),
        ),
    )

    # Assert
    assert sut == 1


@pytest.mark.asyncio
async def test_unscheduled_task_matches_due_filter(task_service: TaskService) -> None:
    # Arrange
    unscheduled = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}due-filter-unscheduled",
            due_at=datetime(2099, 8, 6, 12, 0),
        ),
    )
    await create_task(
        task_service,
        title="due-filter-scheduled-outside",
        due_at=datetime(2099, 8, 7, 12, 0),
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 8, 6, 0, 0),
            due_to=datetime(2099, 8, 6, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {unscheduled.task_id}


@pytest.mark.asyncio
async def test_schedule_filters_exclude_unscheduled_tasks(task_service: TaskService) -> None:
    # Arrange
    scheduled = await create_task(
        task_service,
        title="schedule-filter-scheduled",
        starts_at=datetime(2099, 9, 1, 10, 0),
    )
    unscheduled = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}schedule-filter-unscheduled",
            due_at=datetime(2099, 9, 1, 11, 0),
        ),
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 9, 1, 0, 0),
            starts_to=datetime(2099, 9, 1, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    ids = task_ids(sut)
    assert scheduled.task_id in ids
    assert unscheduled.task_id not in ids


@pytest.mark.asyncio
async def test_deleted_tag_is_removed_from_tag_filters(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    task = await create_task(task_service, title="delete-tag-filter")
    first_tag = await create_tag(tag_service, name="delete-tag-filter-first")
    second_tag = await create_tag(tag_service, name="delete-tag-filter-second")
    await task_service.add_tag_to_task(TEST_USER_ID, task.task_id, first_tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, task.task_id, second_tag.tag_id)

    # Act
    await task_service.delete_tag_from_task(TEST_USER_ID, task.task_id, first_tag.tag_id)
    first_tag_tasks = await task_service.get_tasks(
        TEST_USER_ID, ListTasksFilters(tag_ids=(first_tag.tag_id,), limit=1000)
    )
    second_tag_tasks = await task_service.get_tasks(
        TEST_USER_ID, ListTasksFilters(tag_ids=(second_tag.tag_id,), limit=1000)
    )

    # Assert
    assert task.task_id not in task_ids(first_tag_tasks)
    assert task.task_id in task_ids(second_tag_tasks)


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_combined_criteria(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="combined-filter")
    matching = await create_task(
        task_service,
        title="combined-filter-match",
        description="quarterly invoice review",
        due_at=datetime(2099, 10, 1, 12, 0),
        starts_at=datetime(2099, 10, 1, 10, 0),
        status=TaskStatus.ACTIVE,
    )
    wrong_status = await create_task(
        task_service,
        title="combined-filter-completed",
        description="quarterly invoice review",
        due_at=datetime(2099, 10, 1, 12, 0),
        starts_at=datetime(2099, 10, 1, 12, 0),
        status=TaskStatus.COMPLETED,
    )
    wrong_text = await create_task(
        task_service,
        title="combined-filter-wrong-text",
        description="quarterly roadmap review",
        due_at=datetime(2099, 10, 1, 12, 0),
        starts_at=datetime(2099, 10, 1, 14, 0),
        status=TaskStatus.ACTIVE,
    )
    await task_service.add_tag_to_task(TEST_USER_ID, matching.task_id, tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, wrong_status.task_id, tag.tag_id)
    await task_service.add_tag_to_task(TEST_USER_ID, wrong_text.task_id, tag.tag_id)

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            tag_ids=(tag.tag_id,),
            statuses=(TaskStatus.ACTIVE,),
            search_text="invoice",
            due_from=datetime(2099, 10, 1, 0, 0),
            due_to=datetime(2099, 10, 1, 23, 59),
            starts_from=datetime(2099, 10, 1, 0, 0),
            starts_to=datetime(2099, 10, 1, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_tag_filter(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    matching = await create_task(task_service, title="tag-count-match")
    await create_task(task_service, title="tag-count-other")
    tag = await create_tag(tag_service, name="task-count-filter")
    await task_service.add_tag_to_task(TEST_USER_ID, matching.task_id, tag.tag_id)

    # Act
    sut = await task_service.count_tasks(TEST_USER_ID, ListTasksFilters(tag_ids=(tag.tag_id,)))

    # Assert
    assert sut == 1


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_search_text_in_title(
    task_service: TaskService,
) -> None:
    # Arrange
    matching = await create_task(task_service, title="quarterly roadmap")
    await create_task(task_service, title="weekly planning")

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            search_text="roadmap",
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_search_text_in_description(
    task_service: TaskService,
) -> None:
    # Arrange
    matching = await create_task(
        task_service,
        title="client notes",
        description="Prepare invoice reconciliation",
    )
    await create_task(
        task_service,
        title="team notes",
        description="Prepare meeting agenda",
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            search_text="invoice",
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_search_text(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="search count target")
    await create_task(task_service, title="another task")

    # Act
    sut = await task_service.count_tasks(TEST_USER_ID, ListTasksFilters(search_text="target"))

    # Assert
    assert sut == 1


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_start_lower_bound(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="starts-before", starts_at=datetime(2099, 2, 1, 10, 0))
    matching = await create_task(
        task_service, title="starts-after", starts_at=datetime(2099, 2, 2, 10, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 2, 2, 0, 0),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_start_upper_bound(task_service: TaskService) -> None:
    # Arrange
    matching = await create_task(
        task_service, title="starts-before-limit", starts_at=datetime(2099, 3, 1, 10, 0)
    )
    await create_task(
        task_service, title="starts-after-limit", starts_at=datetime(2099, 3, 2, 10, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_to=datetime(2099, 3, 1, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_end_lower_bound(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="ends-before", starts_at=datetime(2099, 4, 1, 10, 0))
    matching = await create_task(
        task_service, title="ends-after", starts_at=datetime(2099, 4, 2, 10, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            ends_from=datetime(2099, 4, 2, 10, 30),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_filter_tasks_by_end_upper_bound(task_service: TaskService) -> None:
    # Arrange
    matching = await create_task(
        task_service, title="ends-before-limit", starts_at=datetime(2099, 12, 1, 10, 0)
    )
    await create_task(
        task_service, title="ends-after-limit", starts_at=datetime(2099, 12, 2, 10, 0)
    )

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            ends_to=datetime(2099, 12, 1, 11, 30),
            limit=1000,
        ),
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_paginate_filtered_tasks(task_service: TaskService) -> None:
    # Arrange
    first = await create_task(
        task_service, title="page-first", starts_at=datetime(2099, 1, 1, 10, 0)
    )
    second = await create_task(
        task_service, title="page-second", starts_at=datetime(2099, 1, 2, 10, 0)
    )
    await create_task(task_service, title="page-third", starts_at=datetime(2099, 1, 3, 10, 0))

    # Act
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 1, 1),
            starts_to=datetime(2099, 1, 4),
            limit=1,
            offset=1,
        ),
    )

    # Assert
    assert task_ids(sut) == {second.task_id}
    assert first.task_id not in task_ids(sut)


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_filter(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="counted", starts_at=datetime(2099, 6, 1, 10, 0))
    await create_task(task_service, title="not-counted", starts_at=datetime(2099, 7, 1, 10, 0))

    # Act
    sut = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE,),
            starts_from=datetime(2099, 6, 1),
            starts_to=datetime(2099, 6, 2),
        ),
    )

    # Assert
    assert sut == 1


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_end_filter(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="end-counted", starts_at=datetime(2099, 10, 1, 10, 0))
    await create_task(task_service, title="end-not-counted", starts_at=datetime(2099, 11, 1, 10, 0))

    # Act
    sut = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE,),
            ends_from=datetime(2099, 10, 1, 10, 30),
            ends_to=datetime(2099, 10, 1, 11, 30),
        ),
    )

    # Assert
    assert sut == 1
