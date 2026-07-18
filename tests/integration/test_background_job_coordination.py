from datetime import date
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from config import CeleryConfig, settings
from adapters.background_job_coordination import RedisBackgroundJobCoordinator
from adapters.key_value_store import create_key_value_store_client
from workers.coordination import BackgroundJobClaimStatus


@pytest.mark.asyncio
async def test_redis_coordinates_and_remembers_a_completed_background_run() -> None:
    key_prefix = f"task-manager:test:background-job:{uuid4().hex}"
    config = CeleryConfig(
        **{
            **settings.celery.model_dump(),
            "coordination_key_prefix": key_prefix,
        }
    )
    first_client = create_key_value_store_client(
        settings.key_value_store,
        max_connections=config.coordination_max_connections,
    )
    second_client = create_key_value_store_client(
        settings.key_value_store,
        max_connections=config.coordination_max_connections,
    )
    scheduled_date = date(2099, 1, 1)
    redis_available = False

    try:
        try:
            await first_client.ping()
        except RedisError as exc:
            pytest.skip(f"Redis is not available: {exc}")
        redis_available = True

        first = RedisBackgroundJobCoordinator(first_client, config)
        second = RedisBackgroundJobCoordinator(second_client, config)

        acquired = await first.claim("recurrence-materialization", scheduled_date)
        competing = await second.claim("recurrence-materialization", scheduled_date)

        assert acquired.status is BackgroundJobClaimStatus.ACQUIRED
        assert acquired.lease is not None
        assert competing.status is BackgroundJobClaimStatus.ALREADY_RUNNING

        await acquired.lease.complete()

        repeated = await second.claim("recurrence-materialization", scheduled_date)
        assert repeated.status is BackgroundJobClaimStatus.ALREADY_COMPLETED
    finally:
        if redis_available:
            await first_client.delete(
                f"{key_prefix}:lease:recurrence-materialization:{scheduled_date.isoformat()}",
                f"{key_prefix}:completed:recurrence-materialization:{scheduled_date.isoformat()}",
            )
        await first_client.aclose()
        await second_client.aclose()
