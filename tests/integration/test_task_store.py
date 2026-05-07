from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from constants import TEST_TITLE_PREFIX
from dto.tasks import AddTask, UpdateTaskData
from services.tasks import TaskService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_task_store_is_created_for_new_task(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 5, 10, 0)

    # Act
    task = await task_service.create_task(
        AddTask(
            title=f"{TEST_TITLE_PREFIX}search-create",
            description="Findable search content",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )
    )

    # Assert
    assert await task_store_matches(test_engine, task.task_id, "findable")


@pytest.mark.asyncio
async def test_task_store_is_updated_when_task_text_changes(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    starts_at = datetime(2099, 5, 5, 10, 0)
    task = await task_service.create_task(
        AddTask(
            title=f"{TEST_TITLE_PREFIX}search-update",
            description="Initial search content",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )
    )

    # Act
    await task_service.update_task(
        task.task_id,
        UpdateTaskData(description="Updated searchable content"),
    )

    # Assert
    assert await task_store_matches(test_engine, task.task_id, "searchable")


async def task_store_matches(engine: AsyncEngine, task_id, query: str) -> bool:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM task_store
                    WHERE
                        task_id = :task_id AND
                        tsv_content @@ plainto_tsquery('russian', :query)
                )
            """),
            {"task_id": task_id, "query": query},
        )
        return result.scalar_one()
