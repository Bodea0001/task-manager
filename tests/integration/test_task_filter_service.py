from datetime import datetime

import pytest

from helpers import create_tag, create_task, task_ids, task_ids_with_test_prefix

from dto.tasks import ListTasksFilters
from domain.value_objects.tasks import TaskStatus
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
        ListTasksFilters(
            starts_from=datetime(2099, 8, 2, 0, 0),
            ends_to=datetime(2099, 8, 2, 11, 30),
            limit=1000,
        )
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
        ListTasksFilters(
            starts_to=datetime(2099, 8, 3, 10, 30),
            ends_from=datetime(2099, 8, 3, 10, 30),
            limit=1000,
        )
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
        starts_at=datetime(2099, 8, 5, 9, 59),
        ends_at=ends_at,
    )
    await create_task(
        task_service,
        title="time-boundary-after-end",
        starts_at=starts_at,
        ends_at=datetime(2099, 8, 5, 12, 1),
    )

    # Act
    sut = await task_service.get_tasks(
        ListTasksFilters(
            starts_from=starts_at,
            starts_to=starts_at,
            ends_from=ends_at,
            ends_to=ends_at,
            limit=1000,
        )
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
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE, TaskStatus.COMPLETED),
            limit=1000,
        )
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {active.task_id, completed.task_id}


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
    await task_service.add_tag_to_task(matching.task_id, tag.tag_id)
    await task_service.add_tag_to_task(other.task_id, other_tag.tag_id)

    # Act
    sut = await task_service.get_tasks(
        ListTasksFilters(
            tag_ids=(tag.tag_id,),
            limit=1000,
        )
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
    await task_service.add_tag_to_task(first.task_id, first_tag.tag_id)
    await task_service.add_tag_to_task(second.task_id, second_tag.tag_id)

    # Act
    sut = await task_service.get_tasks(
        ListTasksFilters(
            tag_ids=(first_tag.tag_id, second_tag.tag_id),
            limit=1000,
        )
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {first.task_id, second.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_tag_filter(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    matching = await create_task(task_service, title="tag-count-match")
    await create_task(task_service, title="tag-count-other")
    tag = await create_tag(tag_service, name="task-count-filter")
    await task_service.add_tag_to_task(matching.task_id, tag.tag_id)

    # Act
    sut = await task_service.count_tasks(ListTasksFilters(tag_ids=(tag.tag_id,)))

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
        ListTasksFilters(
            search_text="roadmap",
            limit=1000,
        )
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
        ListTasksFilters(
            search_text="invoice",
            limit=1000,
        )
    )

    # Assert
    assert task_ids_with_test_prefix(sut) == {matching.task_id}


@pytest.mark.asyncio
async def test_user_can_count_tasks_matching_search_text(task_service: TaskService) -> None:
    # Arrange
    await create_task(task_service, title="search count target")
    await create_task(task_service, title="another task")

    # Act
    sut = await task_service.count_tasks(ListTasksFilters(search_text="target"))

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
        ListTasksFilters(
            starts_from=datetime(2099, 2, 2, 0, 0),
            limit=1000,
        )
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
        ListTasksFilters(
            starts_to=datetime(2099, 3, 1, 23, 59),
            limit=1000,
        )
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
        ListTasksFilters(
            ends_from=datetime(2099, 4, 2, 10, 30),
            limit=1000,
        )
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
        ListTasksFilters(
            ends_to=datetime(2099, 12, 1, 11, 30),
            limit=1000,
        )
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
        ListTasksFilters(
            starts_from=datetime(2099, 1, 1),
            starts_to=datetime(2099, 1, 4),
            limit=1,
            offset=1,
        )
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
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE,),
            starts_from=datetime(2099, 6, 1),
            starts_to=datetime(2099, 6, 2),
        )
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
        ListTasksFilters(
            statuses=(TaskStatus.ACTIVE,),
            ends_from=datetime(2099, 10, 1, 10, 30),
            ends_to=datetime(2099, 10, 1, 11, 30),
        )
    )

    # Assert
    assert sut == 1
