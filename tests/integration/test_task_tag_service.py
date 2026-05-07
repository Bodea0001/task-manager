from uuid import uuid4

import pytest

from helpers import create_tag, create_task, tag_ids
from constants import TEST_TITLE_PREFIX

from dto.tasks import ListTasksFilters
from services.tags import TagService
from services.tasks import TaskService
from exceptions import TagNotFound, TaskNotFound


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_add_tag_to_task(task_service: TaskService, tag_service: TagService) -> None:
    # Arrange
    task = await create_task(task_service, title="add-tag")
    tag = await create_tag(tag_service, name="add-to-task")

    # Act
    sut = await task_service.add_tag_to_task(task.task_id, tag.tag_id)

    # Assert
    assert sut.task_id == task.task_id
    assert tag.tag_id in tag_ids(sut.tags)


@pytest.mark.asyncio
async def test_user_can_open_task_with_tags(
    task_service: TaskService, tag_service: TagService
) -> None:
    # Arrange
    task = await create_task(task_service, title="open-with-tag")
    tag = await create_tag(tag_service, name="open-with-task")
    await task_service.add_tag_to_task(task.task_id, tag.tag_id)

    # Act
    sut = await task_service.get_task(task.task_id)

    # Assert
    assert tag.tag_id in tag_ids(sut.tags)


@pytest.mark.asyncio
async def test_user_can_view_tasks_with_tags(
    task_service: TaskService, tag_service: TagService
) -> None:
    # Arrange
    first_task = await create_task(task_service, title="list-with-first-tag")
    second_task = await create_task(task_service, title="list-with-second-tag")
    first_tag = await create_tag(tag_service, name="list-with-first-task")
    second_tag = await create_tag(tag_service, name="list-with-second-task")
    await task_service.add_tag_to_task(first_task.task_id, first_tag.tag_id)
    await task_service.add_tag_to_task(second_task.task_id, second_tag.tag_id)

    # Act
    tasks = await task_service.get_tasks(ListTasksFilters(limit=1000))
    sut = {item.task_id: item for item in tasks if item.title.startswith(TEST_TITLE_PREFIX)}

    # Assert
    assert set(sut) == {first_task.task_id, second_task.task_id}
    assert tag_ids(sut[first_task.task_id].tags) == {first_tag.tag_id}
    assert tag_ids(sut[second_task.task_id].tags) == {second_tag.tag_id}


@pytest.mark.asyncio
async def test_user_can_delete_tag_from_task(
    task_service: TaskService, tag_service: TagService
) -> None:
    # Arrange
    task = await create_task(task_service, title="delete-tag")
    tag = await create_tag(tag_service, name="delete-from-task")
    await task_service.add_tag_to_task(task.task_id, tag.tag_id)

    # Act
    sut = await task_service.delete_tag_from_task(task.task_id, tag.tag_id)

    # Assert
    assert tag.tag_id not in tag_ids(sut.tags)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ("add_tag_to_task", "delete_tag_from_task"))
async def test_user_cannot_change_tags_on_missing_task(
    task_service: TaskService, tag_service: TagService, action: str
) -> None:
    # Arrange
    tag = await create_tag(tag_service, name=f"{action}-missing-task")

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await getattr(task_service, action)(uuid4(), tag.tag_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ("add_tag_to_task", "delete_tag_from_task"))
async def test_user_cannot_use_missing_tag_for_task(task_service: TaskService, action: str) -> None:
    # Arrange
    task = await create_task(task_service, title=f"{action}-missing-tag")

    # Act / Assert
    with pytest.raises(TagNotFound):
        await getattr(task_service, action)(task.task_id, uuid4())
