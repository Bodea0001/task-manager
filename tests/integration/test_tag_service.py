from uuid import uuid4

import pytest

from helpers import create_tag
from constants import TEST_TAG_PREFIX

from domain.value_objects.tags import Tag
from services.tags import TagService
from exceptions import TagNotFound


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_create_a_tag(tag_service: TagService) -> None:
    # Act
    sut = await tag_service.create_tag(f"{TEST_TAG_PREFIX}create")

    # Assert
    assert sut.tag_id is not None
    assert sut.name == f"{TEST_TAG_PREFIX}create"
    assert sut.created_at is not None


@pytest.mark.asyncio
async def test_user_can_ensure_a_new_tag(tag_service: TagService) -> None:
    # Act
    sut = await tag_service.ensure_tag(f"  {TEST_TAG_PREFIX}Ensured   Tag  ")

    # Assert
    assert sut.tag_id is not None
    assert sut.name == f"{TEST_TAG_PREFIX}ensured tag"


@pytest.mark.asyncio
async def test_user_can_ensure_an_existing_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await tag_service.ensure_tag(f"{TEST_TAG_PREFIX}existing tag")

    # Act
    sut = await tag_service.ensure_tag(f"  {TEST_TAG_PREFIX}Existing   Tag  ")

    # Assert
    assert sut == tag


@pytest.mark.asyncio
async def test_user_can_open_an_existing_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="open")

    # Act
    sut = await tag_service.get_tag(tag.tag_id)

    # Assert
    assert sut == tag


@pytest.mark.asyncio
async def test_user_can_view_tags(tag_service: TagService) -> None:
    # Arrange
    first = await create_tag(tag_service, name="list-first")
    second = await create_tag(tag_service, name="list-second")

    # Act
    sut = await tag_service.get_tags()

    # Assert
    assert tag_ids_with_test_prefix(sut) == {first.tag_id, second.tag_id}


@pytest.mark.asyncio
async def test_user_can_update_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="update")

    # Act
    sut = await tag_service.update_tag(tag.tag_id, f"{TEST_TAG_PREFIX}updated")

    # Assert
    assert sut.tag_id == tag.tag_id
    assert sut.name == f"{TEST_TAG_PREFIX}updated"


@pytest.mark.asyncio
async def test_user_can_delete_tag(tag_service: TagService) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="delete")

    # Act
    await tag_service.delete_tag(tag.tag_id)

    # Assert
    with pytest.raises(TagNotFound):
        await tag_service.get_tag(tag.tag_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ("get_tag", "delete_tag"))
async def test_user_cannot_act_on_missing_tag(tag_service: TagService, action: str) -> None:
    # Act / Assert
    with pytest.raises(TagNotFound):
        await getattr(tag_service, action)(uuid4())


@pytest.mark.asyncio
async def test_user_cannot_update_missing_tag(tag_service: TagService) -> None:
    # Act / Assert
    with pytest.raises(TagNotFound):
        await tag_service.update_tag(uuid4(), f"{TEST_TAG_PREFIX}missing")


def tag_ids_with_test_prefix(tags: list[Tag]) -> set:
    return {tag.tag_id for tag in tags if tag.name.startswith(TEST_TAG_PREFIX)}
