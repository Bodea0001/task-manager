from datetime import datetime

import pytest

from constants import TEST_OTHER_USER_ID, TEST_TAG_PREFIX, TEST_USER_ID
from domain.value_objects.tasks import FreeTime, Schedule
from dto.tasks import AddTask, ListTasksFilters, UpdateTaskData
from exceptions import TagNotFound, TaskNotFound
from helpers import create_tag, create_task, task_ids, tag_ids
from services.tags import TagService
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_view_only_own_tasks(task_service: TaskService) -> None:
    # Arrange
    own_task = await create_task(task_service, title="own-visible")
    other_task = await create_task(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="other-hidden",
    )

    # Act
    tasks = await task_service.get_tasks(TEST_USER_ID, ListTasksFilters(limit=1000))
    count = await task_service.count_tasks(TEST_USER_ID)

    # Assert
    assert own_task.task_id in task_ids(tasks)
    assert other_task.task_id not in task_ids(tasks)
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "payload"),
    (
        ("get_task", ()),
        ("update_task", (UpdateTaskData(title="updated by other user"),)),
        ("delete_task", ()),
        ("delete_schedule_from_task", ()),
    ),
)
async def test_user_cannot_act_on_another_users_task(
    task_service: TaskService,
    action: str,
    payload: tuple,
) -> None:
    # Arrange
    other_task = await create_task(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title=f"foreign-{action}",
    )

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await getattr(task_service, action)(TEST_USER_ID, other_task.task_id, *payload)


@pytest.mark.asyncio
async def test_user_can_view_only_own_tags(tag_service: TagService) -> None:
    # Arrange
    own_tag = await create_tag(tag_service, name="own-visible")
    other_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name="other-hidden",
    )

    # Act
    tags = await tag_service.get_tags(TEST_USER_ID)

    # Assert
    assert own_tag.tag_id in tag_ids(tags)
    assert other_tag.tag_id not in tag_ids(tags)


@pytest.mark.asyncio
async def test_users_can_use_same_tag_name(tag_service: TagService) -> None:
    # Arrange
    tag_name = f"{TEST_TAG_PREFIX}shared name"

    # Act
    own_tag = await tag_service.ensure_tag(TEST_USER_ID, tag_name)
    other_tag = await tag_service.ensure_tag(TEST_OTHER_USER_ID, tag_name)
    ensured_again = await tag_service.ensure_tag(TEST_USER_ID, tag_name)

    # Assert
    assert own_tag.name == other_tag.name
    assert own_tag.tag_id != other_tag.tag_id
    assert ensured_again == own_tag


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ("get_tag", "delete_tag"))
async def test_user_cannot_act_on_another_users_tag(
    tag_service: TagService,
    action: str,
) -> None:
    # Arrange
    other_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name=f"foreign-{action}",
    )

    # Act / Assert
    with pytest.raises(TagNotFound):
        await getattr(tag_service, action)(TEST_USER_ID, other_tag.tag_id)


@pytest.mark.asyncio
async def test_user_cannot_update_another_users_tag(tag_service: TagService) -> None:
    # Arrange
    other_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name="foreign-update",
    )

    # Act / Assert
    with pytest.raises(TagNotFound):
        await tag_service.update_tag(TEST_USER_ID, other_tag.tag_id, "updated")


@pytest.mark.asyncio
async def test_user_cannot_attach_another_users_tag_to_own_task(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    task = await create_task(task_service, title="own-task-foreign-tag")
    other_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name="foreign-tag",
    )

    # Act / Assert
    with pytest.raises(TagNotFound):
        await task_service.add_tag_to_task(TEST_USER_ID, task.task_id, other_tag.tag_id)


@pytest.mark.asyncio
async def test_user_cannot_attach_own_tag_to_another_users_task(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    other_task = await create_task(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="foreign-task-own-tag",
    )
    tag = await create_tag(tag_service, name="own-tag")

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await task_service.add_tag_to_task(TEST_USER_ID, other_task.task_id, tag.tag_id)


@pytest.mark.asyncio
async def test_user_free_time_ignores_another_users_schedule(task_service: TaskService) -> None:
    # Arrange
    window = Schedule(
        starts_at=datetime(2099, 9, 1, 9, 0),
        ends_at=datetime(2099, 9, 1, 18, 0),
    )
    await create_task(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="foreign-busy-window",
        starts_at=window.starts_at,
        ends_at=window.ends_at,
    )

    # Act
    sut = await task_service.get_free_time(TEST_USER_ID, window)

    # Assert
    assert sut == [FreeTime(starts_at=window.starts_at, ends_at=window.ends_at)]


@pytest.mark.asyncio
async def test_schedule_availability_ignores_another_users_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    window = Schedule(
        starts_at=datetime(2099, 9, 2, 9, 0),
        ends_at=datetime(2099, 9, 2, 18, 0),
    )
    await create_task(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="foreign-availability-window",
        starts_at=window.starts_at,
        ends_at=window.ends_at,
    )

    # Act
    sut = await task_service.check_schedule_availability(TEST_USER_ID, window)

    # Assert
    assert sut.can_add_task
    assert sut.blocking_tasks == []


@pytest.mark.asyncio
async def test_user_schedule_can_overlap_another_users_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    schedule = Schedule(
        starts_at=datetime(2099, 9, 2, 10, 0),
        ends_at=datetime(2099, 9, 2, 11, 0),
    )
    await create_task(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="foreign-overlap",
        starts_at=schedule.starts_at,
        ends_at=schedule.ends_at,
    )

    # Act
    sut = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title="own-overlap",
            due_at=schedule.ends_at,
            schedule=schedule,
        ),
    )

    # Assert
    assert sut.schedule == schedule
