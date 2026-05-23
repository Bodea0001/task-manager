from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from constants import TEST_TITLE_PREFIX, TEST_USER_ID
from dto.tasks import AddTask, ListTasksFilters, UpdateTaskData
from helpers import create_tag, create_task, tag_ids
from domain.value_objects.tasks import Schedule, TaskPriority, TaskStatus
from exceptions import TagNotFound, TaskNotFound, TaskScheduleOverlap
from services.tags import TagService
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_create_a_task(task_service: TaskService) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act
    sut = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}create",
            due_at=ends_at,
            description="Initial description",
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
        ),
    )

    # Assert
    assert sut.task_id is not None
    assert sut.title == f"{TEST_TITLE_PREFIX}create"
    assert sut.description == "Initial description"
    assert sut.status == TaskStatus.ACTIVE
    assert sut.priority == TaskPriority.NORMAL
    assert sut.due_at == ends_at
    assert sut.schedule == Schedule(starts_at=starts_at, ends_at=ends_at)


@pytest.mark.asyncio
async def test_user_can_create_an_unscheduled_task(task_service: TaskService) -> None:
    # Arrange
    due_at = datetime(2099, 5, 5, 11, 0)

    # Act
    sut = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}create-unscheduled",
            due_at=due_at,
            description="Initial description",
        ),
    )

    # Assert
    assert sut.due_at == due_at
    assert sut.schedule is None


@pytest.mark.asyncio
async def test_user_can_create_a_task_with_tags(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="create-with-task")
    starts_at = datetime(2099, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act
    sut = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}create-with-tags",
            due_at=ends_at,
            description="Initial description",
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
            tag_ids=(tag.tag_id,),
        ),
    )

    # Assert
    assert tag_ids(sut.tags) == {tag.tag_id}


@pytest.mark.asyncio
async def test_user_cannot_create_a_task_with_missing_tag(task_service: TaskService) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act / Assert
    with pytest.raises(TagNotFound):
        await task_service.create_task(
            TEST_USER_ID,
            AddTask(
                title=f"{TEST_TITLE_PREFIX}create-with-missing-tag",
                due_at=ends_at,
                description="Initial description",
                schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
                tag_ids=(uuid4(),),
            ),
        )


@pytest.mark.asyncio
async def test_user_cannot_create_task_with_overlapping_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 6, 10, 0)
    await create_task(
        task_service,
        title="overlap-create-existing",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
    )

    # Act / Assert
    with pytest.raises(TaskScheduleOverlap):
        await task_service.create_task(
            TEST_USER_ID,
            AddTask(
                title=f"{TEST_TITLE_PREFIX}overlap-create-new",
                due_at=starts_at + timedelta(hours=2),
                schedule=Schedule(
                    starts_at=starts_at + timedelta(minutes=30),
                    ends_at=starts_at + timedelta(hours=1, minutes=30),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_user_can_create_tasks_with_touching_schedule_boundaries(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 7, 10, 0)
    first = await create_task(
        task_service,
        title="touching-boundary-first",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Act
    second = await create_task(
        task_service,
        title="touching-boundary-second",
        starts_at=starts_at + timedelta(hours=1),
        ends_at=starts_at + timedelta(hours=2),
    )

    # Assert
    assert first.schedule is not None
    assert second.schedule is not None
    assert first.schedule.ends_at == second.schedule.starts_at


@pytest.mark.asyncio
async def test_user_can_open_an_existing_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="open")

    # Act
    sut = await task_service.get_task(TEST_USER_ID, task.task_id)

    # Assert
    assert sut == task


@pytest.mark.asyncio
async def test_user_can_update_task_details(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="update")
    assert task.schedule is not None
    new_schedule = Schedule(
        starts_at=task.schedule.starts_at,
        ends_at=task.schedule.ends_at + timedelta(hours=2),
    )

    # Act
    sut = await task_service.update_task(
        TEST_USER_ID,
        task.task_id,
        UpdateTaskData(
            title=f"{TEST_TITLE_PREFIX}updated",
            description="Updated description",
            schedule=new_schedule,
        ),
    )

    # Assert
    assert sut.task_id == task.task_id
    assert sut.title == f"{TEST_TITLE_PREFIX}updated"
    assert sut.description == "Updated description"
    assert sut.schedule == new_schedule


@pytest.mark.asyncio
async def test_user_can_update_task_due_date(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="update-due")
    new_due_at = datetime(2099, 6, 1, 12, 0)

    # Act
    sut = await task_service.update_task(
        TEST_USER_ID,
        task.task_id,
        UpdateTaskData(due_at=new_due_at),
    )

    # Assert
    assert sut.task_id == task.task_id
    assert sut.due_at == new_due_at
    assert sut.schedule == task.schedule


@pytest.mark.asyncio
async def test_user_can_update_task_priority(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="update-priority")

    # Act
    sut = await task_service.update_task(
        TEST_USER_ID,
        task.task_id,
        UpdateTaskData(priority=TaskPriority.URGENT),
    )

    # Assert
    assert sut.task_id == task.task_id
    assert sut.priority == TaskPriority.URGENT
    assert sut.status == task.status


@pytest.mark.asyncio
async def test_user_can_update_task_due_date_and_schedule_together(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await create_task(task_service, title="update-due-and-schedule")
    new_due_at = datetime(2099, 6, 2, 12, 0)
    new_schedule = Schedule(
        starts_at=datetime(2099, 6, 2, 10, 0),
        ends_at=datetime(2099, 6, 2, 11, 30),
    )

    # Act
    sut = await task_service.update_task(
        TEST_USER_ID,
        task.task_id,
        UpdateTaskData(due_at=new_due_at, schedule=new_schedule),
    )

    # Assert
    assert sut.task_id == task.task_id
    assert sut.due_at == new_due_at
    assert sut.schedule == new_schedule


@pytest.mark.asyncio
async def test_user_can_add_schedule_to_unscheduled_task(task_service: TaskService) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}schedule-unscheduled",
            due_at=datetime(2099, 5, 5, 11, 0),
            description="Initial description",
        ),
    )
    schedule = Schedule(
        starts_at=datetime(2099, 5, 5, 10, 0),
        ends_at=datetime(2099, 5, 5, 11, 0),
    )

    # Act
    sut = await task_service.update_task(
        TEST_USER_ID, task.task_id, UpdateTaskData(schedule=schedule)
    )

    # Assert
    assert task.schedule is None
    assert sut.schedule == schedule


@pytest.mark.asyncio
async def test_user_cannot_add_overlapping_schedule_to_unscheduled_task(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 8, 10, 0)
    await create_task(
        task_service,
        title="overlap-add-schedule-existing",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
    )
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}overlap-add-schedule-unscheduled",
            due_at=starts_at + timedelta(hours=1),
        ),
    )

    # Act / Assert
    with pytest.raises(TaskScheduleOverlap):
        await task_service.update_task(
            TEST_USER_ID,
            task.task_id,
            UpdateTaskData(
                schedule=Schedule(
                    starts_at=starts_at + timedelta(minutes=15),
                    ends_at=starts_at + timedelta(minutes=45),
                )
            ),
        )


@pytest.mark.asyncio
async def test_user_can_replace_existing_task_schedule(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="replace-schedule")
    new_schedule = Schedule(
        starts_at=datetime(2099, 5, 6, 14, 0),
        ends_at=datetime(2099, 5, 6, 15, 30),
    )

    # Act
    sut = await task_service.update_task(
        TEST_USER_ID, task.task_id, UpdateTaskData(schedule=new_schedule)
    )

    # Assert
    assert sut.task_id == task.task_id
    assert sut.schedule == new_schedule


@pytest.mark.asyncio
async def test_user_cannot_update_task_schedule_to_overlap_another_task(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 9, 10, 0)
    task = await create_task(
        task_service,
        title="overlap-update-target",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )
    await create_task(
        task_service,
        title="overlap-update-existing",
        starts_at=starts_at + timedelta(hours=2),
        ends_at=starts_at + timedelta(hours=3),
    )

    # Act / Assert
    with pytest.raises(TaskScheduleOverlap):
        await task_service.update_task(
            TEST_USER_ID,
            task.task_id,
            UpdateTaskData(
                schedule=Schedule(
                    starts_at=starts_at + timedelta(hours=2, minutes=15),
                    ends_at=starts_at + timedelta(hours=2, minutes=45),
                )
            ),
        )


@pytest.mark.asyncio
async def test_user_can_delete_task_schedule(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(
        task_service,
        title="delete-schedule",
        starts_at=datetime(2099, 6, 3, 10, 0),
    )
    assert task.schedule is not None

    # Act
    sut = await task_service.delete_schedule_from_task(TEST_USER_ID, task.task_id)

    # Assert
    assert sut.task_id == task.task_id
    assert sut.due_at == task.due_at
    assert sut.schedule is None


@pytest.mark.asyncio
async def test_deleting_task_schedule_removes_it_from_schedule_filters(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 6, 4, 10, 0)
    task = await create_task(
        task_service,
        title="delete-schedule-filter",
        starts_at=starts_at,
    )

    # Act
    await task_service.delete_schedule_from_task(TEST_USER_ID, task.task_id)
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 6, 4, 0, 0),
            starts_to=datetime(2099, 6, 4, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task.task_id not in {item.task_id for item in sut.tasks}


@pytest.mark.asyncio
async def test_user_can_delete_missing_schedule_from_task(task_service: TaskService) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}delete-missing-schedule",
            due_at=datetime(2099, 6, 5, 11, 0),
        ),
    )

    # Act
    sut = await task_service.delete_schedule_from_task(TEST_USER_ID, task.task_id)

    # Assert
    assert task.schedule is None
    assert sut.schedule is None
    assert sut.due_at == task.due_at


@pytest.mark.asyncio
async def test_user_can_complete_a_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="complete")

    # Act
    sut = await task_service.complete_task(TEST_USER_ID, task.task_id)

    # Assert
    assert sut.status == TaskStatus.COMPLETED
    assert sut.completed_at is not None


@pytest.mark.asyncio
async def test_user_can_reopen_a_completed_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="reopen", status=TaskStatus.COMPLETED)

    # Act
    sut = await task_service.reopen_task(TEST_USER_ID, task.task_id)

    # Assert
    assert sut.status == TaskStatus.ACTIVE
    assert sut.completed_at is None


@pytest.mark.asyncio
async def test_user_can_cancel_a_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="cancel")

    # Act
    sut = await task_service.cancel_task(TEST_USER_ID, task.task_id)

    # Assert
    assert sut.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_user_can_delete_a_task(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    task = await create_task(task_service, title="delete")

    # Act
    await task_service.delete_task(TEST_USER_ID, task.task_id)

    # Assert
    with pytest.raises(TaskNotFound):
        await task_service.get_task(TEST_USER_ID, task.task_id)

    async with test_engine.connect() as connection:
        result = await connection.execute(
            text("""
                SELECT deleted_at IS NOT NULL
                FROM task
                WHERE task_id = :task_id
            """),
            {"task_id": task.task_id},
        )
        assert result.scalar_one()


@pytest.mark.asyncio
async def test_deleting_task_removes_it_from_schedule_filters(task_service: TaskService) -> None:
    # Arrange
    starts_at = datetime(2099, 7, 1, 10, 0)
    task = await create_task(
        task_service,
        title="delete-scheduled",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Act
    await task_service.delete_task(TEST_USER_ID, task.task_id)
    sut = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 7, 1, 0, 0),
            starts_to=datetime(2099, 7, 1, 23, 59),
            limit=1000,
        ),
    )

    # Assert
    assert task.task_id not in {item.task_id for item in sut.tasks}
    with pytest.raises(TaskNotFound):
        await task_service.get_task(TEST_USER_ID, task.task_id)


@pytest.mark.asyncio
async def test_deleted_task_is_excluded_from_task_list_and_count(
    task_service: TaskService,
) -> None:
    # Arrange
    deleted_task = await create_task(task_service, title="deleted-list-count")
    visible_task = await create_task(task_service, title="visible-list-count")

    # Act
    await task_service.delete_task(TEST_USER_ID, deleted_task.task_id)
    tasks = await task_service.get_tasks(TEST_USER_ID, ListTasksFilters(limit=1000))
    count = await task_service.count_tasks(TEST_USER_ID)

    # Assert
    listed_task_ids = {task.task_id for task in tasks.tasks}
    assert deleted_task.task_id not in listed_task_ids
    assert visible_task.task_id in listed_task_ids
    assert count == 1


@pytest.mark.asyncio
async def test_deleted_task_is_excluded_from_overdue_tasks(task_service: TaskService) -> None:
    # Arrange
    overdue_at = datetime(2026, 1, 1, 10, 0)
    deleted_task = await create_task(
        task_service,
        title="deleted-overdue",
        due_at=overdue_at,
        starts_at=overdue_at - timedelta(hours=1),
        ends_at=overdue_at,
    )
    visible_task = await create_task(
        task_service,
        title="visible-overdue",
        due_at=overdue_at + timedelta(hours=1),
        starts_at=overdue_at + timedelta(hours=1),
        ends_at=overdue_at + timedelta(hours=2),
    )

    # Act
    await task_service.delete_task(TEST_USER_ID, deleted_task.task_id)
    tasks = await task_service.get_overdue_tasks(TEST_USER_ID, limit=1000)

    # Assert
    overdue_task_ids = {task.task_id for task in tasks}
    assert deleted_task.task_id not in overdue_task_ids
    assert visible_task.task_id in overdue_task_ids


@pytest.mark.asyncio
async def test_deleted_task_does_not_block_schedule_interval(task_service: TaskService) -> None:
    # Arrange
    starts_at = datetime(2099, 7, 2, 10, 0)
    task = await create_task(
        task_service,
        title="delete-release-schedule",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Act
    await task_service.delete_task(TEST_USER_ID, task.task_id)
    sut = await create_task(
        task_service,
        title="reused-deleted-schedule",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Assert
    assert sut.task_id != task.task_id


@pytest.mark.asyncio
async def test_deleted_task_does_not_block_schedule_availability(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 7, 3, 10, 0)
    task = await create_task(
        task_service,
        title="delete-release-availability",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Act
    await task_service.delete_task(TEST_USER_ID, task.task_id)
    sut = await task_service.check_schedule_availability(
        TEST_USER_ID,
        Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
    )

    # Assert
    assert sut.can_add_task
    assert sut.blocking_tasks == []


@pytest.mark.asyncio
async def test_deleted_task_does_not_affect_nearest_free_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    starts_at = datetime(2099, 7, 4, 10, 0)
    task = await create_task(
        task_service,
        title="delete-release-nearest-free",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Act
    await task_service.delete_task(TEST_USER_ID, task.task_id)
    sut = await task_service.find_nearest_free_schedule(
        TEST_USER_ID,
        duration=timedelta(minutes=30),
        search_from=starts_at,
    )

    # Assert
    assert sut == Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    (
        "get_task",
        "complete_task",
        "reopen_task",
        "cancel_task",
        "delete_task",
        "delete_schedule_from_task",
    ),
)
async def test_user_cannot_act_on_missing_task(task_service: TaskService, action: str) -> None:
    # Arrange
    task_id = uuid4()

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await getattr(task_service, action)(TEST_USER_ID, task_id)


@pytest.mark.asyncio
async def test_user_cannot_update_a_missing_task(task_service: TaskService) -> None:
    # Arrange
    task_id = uuid4()

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await task_service.update_task(
            TEST_USER_ID, task_id, UpdateTaskData(title=f"{TEST_TITLE_PREFIX}updated")
        )


@pytest.mark.asyncio
async def test_user_cannot_update_task_with_wrong_interval(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="wrong-update")

    # Act / Assert
    assert task.schedule is not None
    with pytest.raises(ValueError):
        await task_service.update_task(
            TEST_USER_ID,
            task.task_id,
            UpdateTaskData(
                schedule=Schedule(
                    starts_at=task.schedule.starts_at,
                    ends_at=task.schedule.starts_at - timedelta(minutes=1),
                )
            ),
        )
