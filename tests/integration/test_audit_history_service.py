from datetime import datetime, timedelta

import pytest

from constants import TEST_OTHER_USER_ID, TEST_USER_ID
from dto.tasks import UpdateTaskData
from exceptions import TagNotFound, TaskNotFound
from helpers import create_tag, create_task
from domain.value_objects.audit import AuditEventType
from services.tags import TagService
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_task_history_tracks_task_changes(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    task = await create_task(task_service, title="audit-task")
    tag = await create_tag(tag_service, name="audit-task-tag")

    # Act
    await task_service.update_task(
        TEST_USER_ID,
        task.task_id,
        UpdateTaskData(title="updated audit task", due_at=datetime(2099, 8, 1, 12, 0)),
    )
    await task_service.add_tag_to_task(TEST_USER_ID, task.task_id, tag.tag_id)
    await task_service.delete_tag_from_task(TEST_USER_ID, task.task_id, tag.tag_id)
    await task_service.delete_task(TEST_USER_ID, task.task_id)
    history = await task_service.get_task_history(TEST_USER_ID, task.task_id)

    # Assert
    assert [event.event_type for event in history] == [
        AuditEventType.TASK_CREATED,
        AuditEventType.TASK_UPDATED,
        AuditEventType.TASK_TAG_ADDED,
        AuditEventType.TASK_TAG_REMOVED,
        AuditEventType.TASK_DELETED,
    ]
    assert history[1].data == {"changed_fields": ["title", "due_at"]}
    assert history[2].data == {"tag_id": str(tag.tag_id)}
    assert all(event.actor_user_id == TEST_USER_ID for event in history)


@pytest.mark.asyncio
async def test_task_history_tracks_schedule_deletion(task_service: TaskService) -> None:
    # Arrange
    starts_at = datetime(2099, 8, 2, 10, 0)
    task = await create_task(
        task_service,
        title="audit-schedule-delete",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    # Act
    await task_service.delete_schedule_from_task(TEST_USER_ID, task.task_id)
    history = await task_service.get_task_history(TEST_USER_ID, task.task_id)

    # Assert
    assert [event.event_type for event in history] == [
        AuditEventType.TASK_CREATED,
        AuditEventType.TASK_SCHEDULE_DELETED,
    ]


@pytest.mark.asyncio
async def test_failed_task_change_does_not_add_audit_event(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    task = await create_task(task_service, title="audit-failed-change")
    other_user_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name="audit-foreign-tag",
    )

    # Act
    with pytest.raises(TagNotFound):
        await task_service.add_tag_to_task(TEST_USER_ID, task.task_id, other_user_tag.tag_id)
    history = await task_service.get_task_history(TEST_USER_ID, task.task_id)

    # Assert
    assert [event.event_type for event in history] == [AuditEventType.TASK_CREATED]


@pytest.mark.asyncio
async def test_task_history_supports_pagination_in_event_order(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await create_task(task_service, title="audit-pagination")
    await task_service.complete_task(TEST_USER_ID, task.task_id)
    await task_service.reopen_task(TEST_USER_ID, task.task_id)
    await task_service.cancel_task(TEST_USER_ID, task.task_id)

    # Act
    history_page = await task_service.get_task_history(
        TEST_USER_ID,
        task.task_id,
        limit=2,
        offset=1,
    )

    # Assert
    assert [event.event_type for event in history_page] == [
        AuditEventType.TASK_UPDATED,
        AuditEventType.TASK_UPDATED,
    ]
    assert [event.data for event in history_page] == [
        {"changed_fields": ["status"]},
        {"changed_fields": ["status"]},
    ]


@pytest.mark.asyncio
async def test_task_status_helpers_add_status_audit_events(task_service: TaskService) -> None:
    # Arrange
    task = await create_task(task_service, title="audit-status-helpers")

    # Act
    await task_service.complete_task(TEST_USER_ID, task.task_id)
    await task_service.reopen_task(TEST_USER_ID, task.task_id)
    await task_service.cancel_task(TEST_USER_ID, task.task_id)
    history = await task_service.get_task_history(TEST_USER_ID, task.task_id)

    # Assert
    assert [event.event_type for event in history] == [
        AuditEventType.TASK_CREATED,
        AuditEventType.TASK_UPDATED,
        AuditEventType.TASK_UPDATED,
        AuditEventType.TASK_UPDATED,
    ]
    assert [event.data for event in history[1:]] == [
        {"changed_fields": ["status"]},
        {"changed_fields": ["status"]},
        {"changed_fields": ["status"]},
    ]


@pytest.mark.asyncio
async def test_tag_history_tracks_tag_changes(tag_service: TagService) -> None:
    # Arrange
    tag = await tag_service.ensure_tag(TEST_USER_ID, "audit tag")

    # Act
    await tag_service.update_tag(TEST_USER_ID, tag.tag_id, "updated audit tag")
    await tag_service.delete_tag(TEST_USER_ID, tag.tag_id)
    history = await tag_service.get_tag_history(TEST_USER_ID, tag.tag_id)

    # Assert
    assert [event.event_type for event in history] == [
        AuditEventType.TAG_CREATED,
        AuditEventType.TAG_UPDATED,
        AuditEventType.TAG_DELETED,
    ]
    assert history[1].data == {"changed_fields": ["name"]}


@pytest.mark.asyncio
async def test_ensure_existing_tag_does_not_add_creation_history(tag_service: TagService) -> None:
    # Arrange
    tag = await tag_service.ensure_tag(TEST_USER_ID, "audit existing tag")

    # Act
    ensured_again = await tag_service.ensure_tag(TEST_USER_ID, " audit   existing   tag ")
    history = await tag_service.get_tag_history(TEST_USER_ID, tag.tag_id)

    # Assert
    assert ensured_again == tag
    assert [event.event_type for event in history] == [AuditEventType.TAG_CREATED]


@pytest.mark.asyncio
async def test_user_cannot_view_another_users_history(
    task_service: TaskService,
    tag_service: TagService,
) -> None:
    # Arrange
    task = await create_task(task_service, user_id=TEST_OTHER_USER_ID, title="foreign-audit-task")
    tag = await create_tag(tag_service, user_id=TEST_OTHER_USER_ID, name="foreign-audit-tag")

    # Act / Assert
    with pytest.raises(TaskNotFound):
        await task_service.get_task_history(TEST_USER_ID, task.task_id)
    with pytest.raises(TagNotFound):
        await tag_service.get_tag_history(TEST_USER_ID, tag.tag_id)
