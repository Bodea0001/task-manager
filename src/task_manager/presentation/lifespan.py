from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from logging import getLogger
from time import perf_counter

from fastapi import FastAPI

from config import settings
from agents.app import AgentApplication
from services.auth import AuthService
from services.chats import ChatService
from services.tags import TagService
from services.tasks import TaskService
from services.users import UserService
from adapters.agent_run_locks import (
    RedisAgentRunLockManager,
    create_coordination_client,
)
from adapters.unitofwork import SQLAlchemyUnitOfWork
from db.database import create_database_engine
from presentation.agent_stream import AgentStreamCoordinator
from presentation.container import ApplicationContainer


logger = getLogger(__name__)


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Own application resources for the lifetime of one server process."""
    startup_started_at = perf_counter()
    try:
        container = await create_application_container()
    except BaseException as exc:
        duration_ms = round((perf_counter() - startup_started_at) * 1_000, 3)
        logger.error(
            "event=application_startup_completed duration_ms=%.3f outcome=error error_type=%s",
            duration_ms,
            type(exc).__name__,
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={
                "event": "application_startup_completed",
                "duration_ms": duration_ms,
                "outcome": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise

    app.state.container = container
    duration_ms = round((perf_counter() - startup_started_at) * 1_000, 3)
    logger.info(
        "event=application_startup_completed duration_ms=%.3f outcome=success "
        "db_pool_size=%d db_max_overflow=%d",
        duration_ms,
        settings.db.pool_size,
        settings.db.max_overflow,
        extra={
            "event": "application_startup_completed",
            "duration_ms": duration_ms,
            "outcome": "success",
            "db_pool_size": settings.db.pool_size,
            "db_max_overflow": settings.db.max_overflow,
        },
    )

    try:
        yield
    finally:
        shutdown_started_at = perf_counter()
        del app.state.container
        try:
            await close_application_container(container)
        except BaseException as exc:
            duration_ms = round((perf_counter() - shutdown_started_at) * 1_000, 3)
            logger.error(
                "event=application_shutdown_completed duration_ms=%.3f outcome=error error_type=%s",
                duration_ms,
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
                extra={
                    "event": "application_shutdown_completed",
                    "duration_ms": duration_ms,
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                },
            )
            raise
        duration_ms = round((perf_counter() - shutdown_started_at) * 1_000, 3)
        logger.info(
            "event=application_shutdown_completed duration_ms=%.3f outcome=success",
            duration_ms,
            extra={
                "event": "application_shutdown_completed",
                "duration_ms": duration_ms,
                "outcome": "success",
            },
        )


async def create_application_container() -> ApplicationContainer:
    """Initialize services and external resources used by HTTP requests."""
    engine = create_database_engine()
    uow = SQLAlchemyUnitOfWork(engine)
    agent = AgentApplication()
    coordination_client = create_coordination_client(settings.coordination)

    try:
        auth_service = AuthService(uow)
        user_service = UserService(uow)
        task_service = TaskService(uow)
        tag_service = TagService(uow)
        chat_service = ChatService(uow)
        await agent.initialize()
        agent_stream = AgentStreamCoordinator(
            agent=agent,
            task_service=task_service,
            tag_service=tag_service,
            chat_service=chat_service,
            run_lock_manager=RedisAgentRunLockManager(
                coordination_client,
                settings.coordination,
            ),
        )
    except BaseException:
        cleanup_error = await _close_resources(
            coordination_client.aclose,
            agent.close,
            engine.dispose,
        )
        if cleanup_error is not None:
            logger.error(
                "event=application_startup_cleanup_failed error_count=%d",
                len(cleanup_error.exceptions),
                exc_info=(
                    type(cleanup_error),
                    cleanup_error,
                    cleanup_error.__traceback__,
                ),
                extra={
                    "event": "application_startup_cleanup_failed",
                    "error_count": len(cleanup_error.exceptions),
                },
            )
        raise

    return ApplicationContainer(
        engine=engine,
        uow=uow,
        auth_service=auth_service,
        user_service=user_service,
        task_service=task_service,
        tag_service=tag_service,
        chat_service=chat_service,
        agent=agent,
        agent_stream=agent_stream,
        coordination_client=coordination_client,
    )


async def close_application_container(container: ApplicationContainer) -> None:
    """Close container resources even if one shutdown operation fails."""
    cleanup_error = await _close_resources(
        container.agent_stream.close,
        container.coordination_client.aclose,
        container.agent.close,
        container.engine.dispose,
    )
    if cleanup_error is not None:
        raise cleanup_error


async def _close_resources(
    *closers: Callable[[], Awaitable[None]],
) -> BaseExceptionGroup | None:
    errors: list[BaseException] = []
    for close in closers:
        try:
            await close()
        except BaseException as exc:
            errors.append(exc)

    if not errors:
        return None
    return BaseExceptionGroup("Application resource cleanup failed", errors)
