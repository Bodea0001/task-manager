from asyncio import sleep
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from config import CoordinationConfig, settings
from adapters.agent_run_locks import (
    RedisAgentRunLockManager,
)
from adapters.key_value_store import create_key_value_store_client


@pytest.mark.asyncio
async def test_redis_lease_coordinates_independent_agent_run_managers() -> None:
    config = CoordinationConfig(
        **{
            **settings.coordination.model_dump(),
            "key_prefix": f"task-manager:test:agent-run:{uuid4().hex}",
            "lease_ttl_seconds": 10,
            "lease_renew_interval_seconds": 1,
        }
    )
    first_client = create_key_value_store_client(
        settings.key_value_store,
        max_connections=config.max_connections,
    )
    second_client = create_key_value_store_client(
        settings.key_value_store,
        max_connections=config.max_connections,
    )
    chat_id = uuid4()

    try:
        try:
            await first_client.ping()
        except RedisError as exc:
            pytest.skip(f"Redis is not available: {exc}")

        first_manager = RedisAgentRunLockManager(first_client, config)
        second_manager = RedisAgentRunLockManager(second_client, config)

        first_lease = await first_manager.acquire(chat_id)
        assert first_lease is not None
        assert await second_manager.acquire(chat_id) is None
        assert await first_lease.renew() is True

        await first_lease.release()
        expiring_lease = await second_manager.acquire(chat_id)
        assert expiring_lease is not None

        await sleep(config.lease_ttl_seconds + 0.1)
        replacement_lease = await first_manager.acquire(chat_id)
        assert replacement_lease is not None
        await replacement_lease.release()
    finally:
        await first_client.aclose()
        await second_client.aclose()
