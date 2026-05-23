import os
from typing import Any
from pathlib import Path
from uuid import UUID
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from constants import TEST_OTHER_USER_ID, TEST_USER_ID


TEST_USER_EMAIL = "test-user@example.com"
TEST_OTHER_USER_EMAIL = "test-other-user@example.com"
TEST_DATABASE_NAME_PARTS = {"test", "testing", "pytest"}
TEST_TABLES = (
    "audit_event",
    "user_refresh_token",
    "task_recurrence_instance_override",
    "task_recurrence_materialization_conflict",
    "task_recurrence_instance",
    "task_recurrence_month_rule",
    "task_recurrence_weekday",
    "task_recurrence_series",
    "task_recurrence_template",
    "task_store",
    "task_tag",
    "scheduled_task",
    "task",
    "tag",
    "user_auth",
    '"user"',
)

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


def _ensure_test_database_name() -> None:
    db_name = os.environ["TASK_CONFIG_DB_NAME"]
    db_name_parts = set(db_name.lower().replace("-", "_").split("_"))

    if TEST_DATABASE_NAME_PARTS.isdisjoint(db_name_parts):
        pytest.fail(
            "Refusing to run PostgreSQL integration tests against "
            f"database {db_name!r}. Use a dedicated test database whose name "
            "contains a separate 'test', 'testing' or 'pytest' part, for "
            "example 'task_manager_test'.",
            pytrace=False,
        )


_ensure_test_database_name()


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
    await _truncate_test_data(test_engine)
    await _create_test_user(test_engine, TEST_USER_ID, TEST_USER_EMAIL)
    await _create_test_user(test_engine, TEST_OTHER_USER_ID, TEST_OTHER_USER_EMAIL)
    yield
    await _truncate_test_data(test_engine)


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


@pytest.fixture
def auth_service(test_engine: AsyncEngine):
    from adapters.unitofwork import SQLAlchemyUnitOfWork
    from services.auth import AuthService

    return AuthService(SQLAlchemyUnitOfWork(test_engine))


@pytest.fixture
def user_service(test_engine: AsyncEngine):
    from adapters.unitofwork import SQLAlchemyUnitOfWork
    from services.users import UserService

    return UserService(SQLAlchemyUnitOfWork(test_engine))


async def _create_test_user(engine: AsyncEngine, user_id: UUID, email: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("""
                INSERT INTO "user"(user_id, first_name, last_name, email)
                VALUES (:user_id, 'Test', 'User', :email)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"user_id": user_id, "email": email},
        )


async def _truncate_test_data(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(f"""
                TRUNCATE TABLE {", ".join(TEST_TABLES)}
                RESTART IDENTITY CASCADE
            """)
        )
