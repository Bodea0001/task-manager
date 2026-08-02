from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import settings
from services.tasks import TaskService
from workers import runtime as runtime_module
from workers.runtime import WorkerRuntime


def _runtime() -> WorkerRuntime:
    return WorkerRuntime(
        settings.db,
        settings.celery,
        settings.key_value_store,
    )


@pytest.mark.asyncio
async def test_worker_runtime_exposes_resources_only_while_entered(monkeypatch) -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    key_value_store_client = SimpleNamespace(aclose=AsyncMock())
    coordinator = object()
    monkeypatch.setattr(runtime_module, "create_database_engine", lambda _config: engine)
    monkeypatch.setattr(
        runtime_module,
        "create_key_value_store_client",
        lambda *_args, **_kwargs: key_value_store_client,
    )
    monkeypatch.setattr(
        runtime_module,
        "RedisBackgroundJobCoordinator",
        lambda *_args, **_kwargs: coordinator,
    )
    runtime = _runtime()

    with pytest.raises(RuntimeError, match="has not been entered"):
        _ = runtime.task_service

    async with runtime as active_runtime:
        assert isinstance(active_runtime.task_service, TaskService)
        assert active_runtime.job_coordinator is coordinator
        with pytest.raises(RuntimeError, match="entered twice"):
            async with runtime:
                pass

    with pytest.raises(RuntimeError, match="has not been entered"):
        _ = runtime.job_coordinator
    key_value_store_client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_runtime_closes_opened_resources_when_composition_fails(monkeypatch) -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    key_value_store_client = SimpleNamespace(aclose=AsyncMock())

    def fail_composition(*_args, **_kwargs):
        raise RuntimeError("composition failed")

    monkeypatch.setattr(runtime_module, "create_database_engine", lambda _config: engine)
    monkeypatch.setattr(
        runtime_module,
        "create_key_value_store_client",
        lambda *_args, **_kwargs: key_value_store_client,
    )
    monkeypatch.setattr(
        runtime_module,
        "RedisBackgroundJobCoordinator",
        fail_composition,
    )

    with pytest.raises(RuntimeError, match="composition failed"):
        async with _runtime():
            pass

    key_value_store_client.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_runtime_disposes_database_when_key_value_store_close_fails(
    monkeypatch,
) -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    key_value_store_client = SimpleNamespace(
        aclose=AsyncMock(side_effect=RuntimeError("key-value store close failed"))
    )
    monkeypatch.setattr(runtime_module, "create_database_engine", lambda _config: engine)
    monkeypatch.setattr(
        runtime_module,
        "create_key_value_store_client",
        lambda *_args, **_kwargs: key_value_store_client,
    )
    monkeypatch.setattr(
        runtime_module,
        "RedisBackgroundJobCoordinator",
        lambda *_args, **_kwargs: object(),
    )

    with pytest.raises(RuntimeError, match="key-value store close failed"):
        async with _runtime():
            pass

    engine.dispose.assert_awaited_once()
