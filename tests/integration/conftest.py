import os
from typing import Any
from pathlib import Path
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from constants import TEST_TAG_PREFIX, TEST_TITLE_PREFIX


REQUIRED_DB_ENV = (
    "TASK_CONFIG_DB_USER",
    "TASK_CONFIG_DB_PASSWORD",
    "TASK_CONFIG_DB_NAME",
)

if any(env_name not in os.environ for env_name in REQUIRED_DB_ENV):
    pytest.skip(
        "PostgreSQL integration tests require TASK_CONFIG_DB_USER, "
        "TASK_CONFIG_DB_PASSWORD and TASK_CONFIG_DB_NAME",
        allow_module_level=True,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Generator[None, Any, Any]:
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))

    try:
        command.upgrade(alembic_config, "head")

        yield

        command.downgrade(alembic_config, "base")
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL is not available: {exc}")


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, Any]:
    from config import settings

    engine = create_async_engine(
        url=settings.db.url,
        poolclass=NullPool,
    )

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_test_tasks(test_engine: AsyncEngine):
    await _delete_test_data(test_engine)
    yield
    await _delete_test_data(test_engine)


@pytest.fixture
def task_service(test_engine: AsyncEngine):
    from adapters.unitofwork import SQLAlchemyUnitOfWork
    from services.tasks import TaskService

    return TaskService(SQLAlchemyUnitOfWork(test_engine))


@pytest.fixture
def tag_service(test_engine: AsyncEngine):
    from adapters.unitofwork import SQLAlchemyUnitOfWork
    from services.tags import TagService

    return TagService(SQLAlchemyUnitOfWork(test_engine))


async def _delete_test_data(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM task WHERE title LIKE :title_prefix"),
            {"title_prefix": f"{TEST_TITLE_PREFIX}%"},
        )
        await connection.execute(
            text("DELETE FROM tag WHERE name LIKE :tag_prefix"),
            {"tag_prefix": f"{TEST_TAG_PREFIX}%"},
        )
