from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from helpers import create_tag, create_task
from constants import TEST_TAG_PREFIX, TEST_USER_ID

from domain.value_objects.tags import Tag
from domain.value_objects.tasks import RecurrenceFrequency, Schedule
from dto.tasks import AddTaskRecurrence, AddTaskRecurrenceTemplate
from services.tags import TagService
from services.tasks import TaskService
from exceptions import TagNotFound


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_create_a_tag(tag_service: TagService) -> None:
    # Act
    sut = await tag_service.create_tag(TEST_USER_ID, f"{TEST_TAG_PREFIX}create")

    # Assert
    assert sut.tag_id is not None
    assert sut.name == f"{TEST_TAG_PREFIX}create"
    assert sut.created_at is not None


@pytest.mark.asyncio
async def test_user_can_ensure_a_new_tag(tag_service: TagService) -> None:
    # Act
    sut = await tag_service.ensure_tag(TEST_USER_ID, f"  {TEST_TAG_PREFIX}Ensured   Tag  ")

    # Assert
    assert sut.tag_id is not None
    assert sut.name == f"{TEST_TAG_PREFIX}ensured tag"


@pytest.mark.asyncio
async def test_user_can_ensure_an_existing_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await tag_service.ensure_tag(TEST_USER_ID, f"{TEST_TAG_PREFIX}existing tag")

    # Act
    sut = await tag_service.ensure_tag(TEST_USER_ID, f"  {TEST_TAG_PREFIX}Existing   Tag  ")

    # Assert
    assert sut == tag


@pytest.mark.asyncio
async def test_user_can_open_an_existing_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="open")

    # Act
    sut = await tag_service.get_tag(TEST_USER_ID, tag.tag_id)

    # Assert
    assert sut == tag


@pytest.mark.asyncio
async def test_user_can_view_tags(tag_service: TagService) -> None:
    # Arrange
    first = await create_tag(tag_service, name="list-first")
    second = await create_tag(tag_service, name="list-second")

    # Act
    sut = await tag_service.get_tags(TEST_USER_ID)

    # Assert
    assert tag_ids_with_test_prefix(sut) == {first.tag_id, second.tag_id}


@pytest.mark.asyncio
async def test_user_can_update_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="update")

    # Act
    sut = await tag_service.update_tag(TEST_USER_ID, tag.tag_id, f"{TEST_TAG_PREFIX}updated")

    # Assert
    assert sut.tag_id == tag.tag_id
    assert sut.name == f"{TEST_TAG_PREFIX}updated"


@pytest.mark.asyncio
async def test_user_can_delete_tag(
    tag_service: TagService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="delete")

    # Act
    await tag_service.delete_tag(TEST_USER_ID, tag.tag_id)

    # Assert
    with pytest.raises(TagNotFound):
        await tag_service.get_tag(TEST_USER_ID, tag.tag_id)

    async with test_engine.connect() as connection:
        result = await connection.execute(
            text("""
                SELECT deleted_at IS NOT NULL
                FROM tag
                WHERE tag_id = :tag_id
            """),
            {"tag_id": tag.tag_id},
        )
        assert result.scalar_one()


@pytest.mark.asyncio
async def test_deleted_tag_is_excluded_from_tag_list(tag_service: TagService) -> None:
    # Arrange
    deleted_tag = await create_tag(tag_service, name="deleted-list")
    visible_tag = await create_tag(tag_service, name="visible-list")

    # Act
    await tag_service.delete_tag(TEST_USER_ID, deleted_tag.tag_id)
    tags = await tag_service.get_tags(TEST_USER_ID)

    # Assert
    listed_tag_ids = tag_ids_with_test_prefix(tags)
    assert deleted_tag.tag_id not in listed_tag_ids
    assert visible_tag.tag_id in listed_tag_ids


@pytest.mark.asyncio
async def test_deleting_tag_removes_task_and_recurrence_template_links(
    tag_service: TagService,
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="delete-links")
    task = await create_task(task_service, title="delete-tag-links", tag_ids=(tag.tag_id,))
    starts_at = task.due_at.replace(year=2099, month=11, day=1)
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TAG_PREFIX}delete-tag-links-template",
            tag_ids=(tag.tag_id,),
            rules=(
                AddTaskRecurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at),
                    occurrences_limit=1,
                ),
            ),
        ),
    )

    # Act
    await tag_service.delete_tag(TEST_USER_ID, tag.tag_id)

    # Assert
    async with test_engine.connect() as connection:
        task_link_count = await connection.scalar(
            text("""
                SELECT count(*)
                FROM task_tag
                WHERE task_id = :task_id AND tag_id = :tag_id
            """),
            {"task_id": task.task_id, "tag_id": tag.tag_id},
        )
        template_link_count = await connection.scalar(
            text("""
                SELECT count(*)
                FROM task_recurrence_template_tag
                WHERE template_id = :template_id AND tag_id = :tag_id
            """),
            {"template_id": template.template_id, "tag_id": tag.tag_id},
        )

    assert task_link_count == 0
    assert template_link_count == 0


@pytest.mark.asyncio
async def test_user_can_create_tag_with_deleted_tag_name(tag_service: TagService) -> None:
    # Arrange
    name = f"{TEST_TAG_PREFIX}recreate-deleted"
    deleted_tag = await tag_service.create_tag(TEST_USER_ID, name)
    await tag_service.delete_tag(TEST_USER_ID, deleted_tag.tag_id)

    # Act
    sut = await tag_service.create_tag(TEST_USER_ID, name)

    # Assert
    assert sut.tag_id != deleted_tag.tag_id
    assert sut.name == name


@pytest.mark.asyncio
async def test_user_can_ensure_tag_with_deleted_tag_name(tag_service: TagService) -> None:
    # Arrange
    name = f"{TEST_TAG_PREFIX}ensure-recreate-deleted"
    deleted_tag = await tag_service.ensure_tag(TEST_USER_ID, name)
    await tag_service.delete_tag(TEST_USER_ID, deleted_tag.tag_id)

    # Act
    sut = await tag_service.ensure_tag(TEST_USER_ID, name)

    # Assert
    assert sut.tag_id != deleted_tag.tag_id
    assert sut.name == name


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ("get_tag", "delete_tag"))
async def test_user_cannot_act_on_missing_tag(tag_service: TagService, action: str) -> None:
    # Act / Assert
    with pytest.raises(TagNotFound):
        await getattr(tag_service, action)(TEST_USER_ID, uuid4())


@pytest.mark.asyncio
async def test_user_cannot_update_missing_tag(tag_service: TagService) -> None:
    # Act / Assert
    with pytest.raises(TagNotFound):
        await tag_service.update_tag(TEST_USER_ID, uuid4(), f"{TEST_TAG_PREFIX}missing")


def tag_ids_with_test_prefix(tags: list[Tag]) -> set:
    return {tag.tag_id for tag in tags if tag.name.startswith(TEST_TAG_PREFIX)}
