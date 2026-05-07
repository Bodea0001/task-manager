from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from constants import TEST_TITLE_PREFIX
from dto.tasks import AddTask, UpdateTaskData
from helpers import create_tag, create_task, tag_ids
from domain.value_objects.tasks import TaskStatus
from exceptions import TagNotFound, TaskNotFound, WrongTaskDeadline
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
        AddTask(
            title=f"{TEST_TITLE_PREFIX}create-with-tags",
            description="Initial description",
            starts_at=starts_at,
            ends_at=ends_at,
            tag_ids=(tag.tag_id,),
        )
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
            AddTask(
                title=f"{TEST_TITLE_PREFIX}create-with-missing-tag",
                description="Initial description",
                starts_at=starts_at,
                ends_at=ends_at,
                tag_ids=(uuid4(),),
            )
        )


@pytest.mark.asyncio
async def test_user_can_open_an_existing_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="open")

    # Act
    sut = await task_service.get_task(task.task_id)

    # Assert
    assert sut == task


@pytest.mark.asyncio
async def test_user_can_update_task_details(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="update")
    new_ends_at = task.ends_at + timedelta(hours=2)

    # Act
    sut = await task_service.update_task(
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
async def test_user_can_complete_a_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="complete")

    # Act
    sut = await task_service.complete_task(task.task_id)

    # Assert
    assert sut.status == TaskStatus.COMPLETED
    assert sut.completed_at is not None


@pytest.mark.asyncio
async def test_user_can_reopen_a_completed_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="reopen", status=TaskStatus.COMPLETED)

    # Act
    sut = await task_service.reopen_task(task.task_id)

    # Assert
    assert sut.status == TaskStatus.ACTIVE
    assert sut.completed_at is None


@pytest.mark.asyncio
async def test_user_can_cancel_a_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="cancel")

    # Act
    sut = await task_service.cancel_task(task.task_id)

    # Assert
    assert sut.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_user_can_delete_a_task(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="delete")

    # Act
    await task_service.delete_task(task.task_id)

    # Assert
    with pytest.raises(TaskNotFound):
        await task_service.get_task(task.task_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ("get_task", "complete_task", "reopen_task", "cancel_task", "delete_task"),
)
async def test_user_cannot_act_on_missing_task(task_service: TaskService, action: str) -> None:
    # Arrange
    task_id = uuid4()

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await getattr(task_service, action)(task_id)


@pytest.mark.asyncio
async def test_user_cannot_update_a_missing_task(task_service: TaskService) -> None:
    # Arrange
    task_id = uuid4()

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await task_service.update_task(task_id, UpdateTaskData(title=f"{TEST_TITLE_PREFIX}updated"))


@pytest.mark.asyncio
async def test_user_cannot_update_task_with_wrong_deadline(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="wrong-update")

    # Act / Assert
    with pytest.raises(WrongTaskDeadline):
        await task_service.update_task(
            task.task_id,
            UpdateTaskData(ends_at=task.starts_at - timedelta(minutes=1)),
        )
