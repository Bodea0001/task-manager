from typing import cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError

import exceptions as app_exc
from config import CoordinationConfig
from agents.run_locks import AgentRunLease


_RENEW_LEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_LEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def create_coordination_client(config: CoordinationConfig) -> Redis:
    """Create one process-wide asynchronous Redis client and connection pool."""
    return Redis.from_url(
        config.redis_url,
        max_connections=config.max_connections,
        socket_connect_timeout=config.connect_timeout_seconds,
        socket_timeout=config.socket_timeout_seconds,
        health_check_interval=config.health_check_interval_seconds,
        decode_responses=True,
    )


class RedisAgentRunLockManager:
    """Coordinate chat-bound runs through expiring token-owned Redis keys."""

    def __init__(self, client: Redis, config: CoordinationConfig) -> None:
        self._client = client
        self._key_prefix = config.key_prefix
        self._ttl_ms = config.lease_ttl_seconds * 1_000
        self._renew_interval_seconds = float(config.lease_renew_interval_seconds)
        self._renew_script = client.register_script(_RENEW_LEASE_SCRIPT)
        self._release_script = client.register_script(_RELEASE_LEASE_SCRIPT)

    async def acquire(self, chat_id: UUID) -> AgentRunLease | None:
        token = uuid4().hex
        key = f"{self._key_prefix}:{{{chat_id}}}"
        try:
            acquired = await self._client.set(
                key,
                token,
                nx=True,
                px=self._ttl_ms,
            )
        except RedisError as exc:
            raise app_exc.AgentCoordinationUnavailable from exc

        if not acquired:
            return None
        return _RedisAgentRunLease(
            key=key,
            token=token,
            ttl_ms=self._ttl_ms,
            renew_interval_seconds=self._renew_interval_seconds,
            renew_script=self._renew_script,
            release_script=self._release_script,
        )


class _RedisAgentRunLease:
    def __init__(
        self,
        *,
        key: str,
        token: str,
        ttl_ms: int,
        renew_interval_seconds: float,
        renew_script: AsyncScript,
        release_script: AsyncScript,
    ) -> None:
        self._key = key
        self._token = token
        self._ttl_ms = ttl_ms
        self._renew_interval_seconds = renew_interval_seconds
        self._renew_script = renew_script
        self._release_script = release_script
        self._released = False

    @property
    def renew_interval_seconds(self) -> float:
        return self._renew_interval_seconds

    async def renew(self) -> bool:
        if self._released:
            return False
        try:
            result = await self._renew_script(
                keys=[self._key],
                args=[self._token, self._ttl_ms],
            )
        except RedisError as exc:
            raise app_exc.AgentCoordinationUnavailable from exc
        return bool(cast(int, result))

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            await self._release_script(
                keys=[self._key],
                args=[self._token],
            )
        except RedisError as exc:
            raise app_exc.AgentCoordinationUnavailable from exc
