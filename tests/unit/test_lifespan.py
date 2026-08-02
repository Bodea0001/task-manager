from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from presentation import lifespan
from presentation.container import ApplicationContainer


class FakeKeyValueStoreClient:
    def __init__(self) -> None:
        self.aclose = AsyncMock()

    def register_script(self, _script: str) -> object:
        return object()


@pytest.mark.asyncio
async def test_application_lifespan_exposes_and_closes_shared_resources(monkeypatch) -> None:
    app = FastAPI()
    container = cast(ApplicationContainer, object())
    create_container = AsyncMock(return_value=container)
    close_container = AsyncMock()
    monkeypatch.setattr(lifespan, "create_application_container", create_container)
    monkeypatch.setattr(lifespan, "close_application_container", close_container)

    async with lifespan.application_lifespan(app):
        assert app.state.container is container

    assert not hasattr(app.state, "container")
    close_container.assert_awaited_once_with(container)


@pytest.mark.asyncio
async def test_failed_startup_closes_every_resource_opened_so_far(monkeypatch) -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    key_value_store_client = FakeKeyValueStoreClient()
    agent = SimpleNamespace(
        initialize=AsyncMock(side_effect=RuntimeError("model startup failed")),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifespan, "create_database_engine", lambda: engine)
    monkeypatch.setattr(
        lifespan,
        "create_key_value_store_client",
        lambda *_args, **_kwargs: key_value_store_client,
    )
    monkeypatch.setattr(lifespan, "AgentApplication", lambda: agent)

    with pytest.raises(RuntimeError, match="model startup failed"):
        await lifespan.create_application_container()

    key_value_store_client.aclose.assert_awaited_once()
    agent.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_attempts_all_resources_and_reports_every_failure() -> None:
    stream = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("stream close failed")))
    key_value_store_client = SimpleNamespace(aclose=AsyncMock())
    agent = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("agent close failed")))
    engine = SimpleNamespace(dispose=AsyncMock())
    container = cast(
        ApplicationContainer,
        SimpleNamespace(
            agent_stream=stream,
            key_value_store_client=key_value_store_client,
            agent=agent,
            engine=engine,
        ),
    )

    with pytest.raises(BaseExceptionGroup) as exc_info:
        await lifespan.close_application_container(container)

    assert len(exc_info.value.exceptions) == 2
    stream.close.assert_awaited_once()
    key_value_store_client.aclose.assert_awaited_once()
    agent.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()
