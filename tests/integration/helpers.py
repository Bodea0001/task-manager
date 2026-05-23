from datetime import datetime, timedelta
from itertools import count
from uuid import UUID
from collections.abc import Iterable

from constants import TEST_TAG_PREFIX, TEST_TITLE_PREFIX, TEST_USER_ID
from domain.value_objects.tags import Tag
from domain.value_objects.tasks import Schedule, Task, TaskPriority, TaskStatus
from dto.tasks import AddTask, TaskList
from services.tags import TagService
from services.tasks import TaskService


_DEFAULT_SCHEDULE_SEQUENCE = count()


async def create_task(
    task_service: TaskService,
    *,
    user_id: UUID = TEST_USER_ID,
    title: str,
    description: str | None = None,
    tag_ids: tuple[UUID, ...] = (),
    due_at: datetime | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    status: TaskStatus = TaskStatus.ACTIVE,
    priority: TaskPriority = TaskPriority.NORMAL,
) -> Task:
    if starts_at is None:
        starts_at = datetime(2099, 5, 5, 10, 0) + timedelta(days=next(_DEFAULT_SCHEDULE_SEQUENCE))

    if ends_at is None:
        ends_at = starts_at + timedelta(hours=1)

    if due_at is None:
        due_at = ends_at

    if description is None:
        description = f"{title} description"

    return await task_service.create_task(
        user_id,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}{title}",
            due_at=due_at,
            description=description,
            tag_ids=tag_ids,
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
            status=status,
            priority=priority,
        ),
    )


async def create_tag(
    tag_service: TagService,
    *,
    user_id: UUID = TEST_USER_ID,
    name: str,
) -> Tag:
    return await tag_service.create_tag(user_id, f"{TEST_TAG_PREFIX}{name}")


def _task_items(tasks: Iterable[Task] | TaskList) -> Iterable[Task]:
    if isinstance(tasks, TaskList):
        return tasks.tasks
    return tasks


def task_ids(tasks: Iterable[Task] | TaskList) -> set:
    tasks = _task_items(tasks)
    return {task.task_id for task in tasks}


def task_ids_with_test_prefix(tasks: Iterable[Task] | TaskList) -> set:
    tasks = _task_items(tasks)
    return {task.task_id for task in tasks if task.title.startswith(TEST_TITLE_PREFIX)}


def tag_ids(tags: list[Tag]) -> set:
    return {tag.tag_id for tag in tags}
