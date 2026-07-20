from asyncio import gather
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from adapters.auth_protection import RedisAnonymousAuthProtection
from adapters.key_value_store import create_key_value_store_client
from config import AuthProtectionConfig, settings


@pytest.mark.asyncio
async def test_auth_protection_coordinates_limits_across_independent_clients() -> None:
    key_prefix = f"task-manager:test:auth-protection:{uuid4().hex}"
    config = AuthProtectionConfig(
        key_prefix=key_prefix,
        login_attempt_limit=2,
        registration_attempt_limit=10,
        attempt_window_seconds=60,
        successful_registration_limit=2,
        registration_reservation_ttl_seconds=30,
    )
    first_client = create_key_value_store_client(
        settings.key_value_store,
        max_connections=2,
    )
    second_client = create_key_value_store_client(
        settings.key_value_store,
        max_connections=2,
    )
    redis_available = False

    try:
        try:
            await first_client.ping()
        except RedisError as exc:
            pytest.skip(f"Redis is not available: {exc}")
        redis_available = True

        first = RedisAnonymousAuthProtection(first_client, config)
        second = RedisAnonymousAuthProtection(second_client, config)
        client_address = "203.0.113.10"

        assert (await first.check_login_attempt(client_address)).allowed is True
        assert (await second.check_login_attempt(client_address)).allowed is True
        limited = await first.check_login_attempt(client_address)
        assert limited.allowed is False
        assert limited.retry_after_seconds is not None

        reservation_results = await gather(
            first.reserve_registration(client_address),
            second.reserve_registration(client_address),
            first.reserve_registration(client_address),
        )
        permits = [permit for permit in reservation_results if permit is not None]
        assert len(permits) == config.successful_registration_limit

        await permits[0].confirm()
        await permits[1].release()

        replacement = await second.reserve_registration(client_address)
        assert replacement is not None
        await replacement.confirm()
        assert await first.reserve_registration(client_address) is None
    finally:
        if redis_available:
            keys = [key async for key in first_client.scan_iter(match=f"{key_prefix}:*")]
            if keys:
                await first_client.delete(*keys)
        await first_client.aclose()
        await second_client.aclose()
