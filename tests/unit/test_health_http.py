import logging
from types import SimpleNamespace, TracebackType
from typing import Self, cast

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import SQLAlchemyError

from presentation.container import ApplicationContainer
from presentation.app import create_app
from presentation.dependencies import get_application_container, get_application_readiness


class DatabaseReadinessProbe:
    def __init__(self, available: bool) -> None:
        self.available = available

    def connect(self) -> Self:
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def execute(self, statement: object) -> None:
        if not self.available:
            raise SQLAlchemyError("Database is unavailable")


class CoordinationReadinessProbe:
    def __init__(self, available: bool) -> None:
        self.available = available

    async def ping(self) -> bool:
        if not self.available:
            raise RedisConnectionError("Coordination is unavailable")
        return True


@pytest.mark.asyncio
async def test_liveness_is_public_and_independent_of_application_resources() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "is_ready, expected_status, expected_body",
    (
        (True, 200, {"status": "ok"}),
        (False, 503, {"status": "unavailable"}),
    ),
)
async def test_readiness_reflects_required_resource_availability(
    is_ready: bool,
    expected_status: int,
    expected_body: dict[str, str],
) -> None:
    app = create_app()
    app.dependency_overrides[get_application_readiness] = lambda: is_ready

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == expected_status
    assert response.json() == expected_body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_ready, database_ready, coordination_ready, expected_status",
    (
        (True, True, True, 200),
        (False, True, True, 503),
        (True, False, True, 503),
        (True, True, False, 503),
    ),
)
async def test_readiness_requires_all_application_resources(
    agent_ready: bool,
    database_ready: bool,
    coordination_ready: bool,
    expected_status: int,
) -> None:
    container = cast(
        ApplicationContainer,
        SimpleNamespace(
            engine=DatabaseReadinessProbe(database_ready),
            coordination_client=CoordinationReadinessProbe(coordination_ready),
            agent=SimpleNamespace(is_initialized=agent_ready),
        ),
    )
    app = create_app()
    app.dependency_overrides[get_application_container] = lambda: container

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == expected_status
    assert response.json()["status"] == ("ok" if expected_status == 200 else "unavailable")


@pytest.mark.asyncio
async def test_readiness_logs_only_state_transitions_above_debug(caplog) -> None:
    readiness_states = iter((False, False, True, True))

    async def readiness() -> bool:
        return next(readiness_states)

    app = create_app()
    app.dependency_overrides[get_application_readiness] = readiness
    caplog.set_level(
        logging.DEBUG,
        logger="presentation.middlewares.request_logging",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        for _ in range(4):
            await client.get("/health/ready")

    records = [
        record
        for record in caplog.records
        if record.name == "presentation.middlewares.request_logging"
        and getattr(record, "path", None) == "/health/ready"
    ]
    assert [record.levelno for record in records] == [
        logging.WARNING,
        logging.DEBUG,
        logging.INFO,
        logging.DEBUG,
    ]
