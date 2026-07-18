from datetime import date
from typing import cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError

from config import CeleryConfig
from workers.coordination import (
    BackgroundJobClaim,
    BackgroundJobClaimStatus,
    BackgroundJobCoordinationUnavailable,
    BackgroundJobLease,
    BackgroundJobLeaseLost,
)


_CLAIM_SCRIPT = """
if redis.call('exists', KEYS[2]) == 1 then
    return 2
end
if redis.call('set', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
    return 1
end
return 0
"""

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

_COMPLETE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('set', KEYS[2], '1', 'PX', ARGV[2])
    redis.call('del', KEYS[1])
    return 1
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class RedisBackgroundJobCoordinator:
    """Coordinate date-scoped background runs through token-owned Redis keys."""

    def __init__(self, client: Redis, config: CeleryConfig) -> None:
        self._client = client
        self._key_prefix = config.coordination_key_prefix
        self._lease_ttl_ms = config.lease_ttl_seconds * 1_000
        self._renew_interval_seconds = float(config.lease_renew_interval_seconds)
        self._completion_ttl_ms = config.completion_ttl_seconds * 1_000
        self._claim_script = client.register_script(_CLAIM_SCRIPT)
        self._renew_script = client.register_script(_RENEW_SCRIPT)
        self._complete_script = client.register_script(_COMPLETE_SCRIPT)
        self._release_script = client.register_script(_RELEASE_SCRIPT)

    async def claim(self, job_name: str, scheduled_date: date) -> BackgroundJobClaim:
        lease_key, completion_key = self._keys(job_name, scheduled_date)
        token = uuid4().hex
        try:
            result = await self._claim_script(
                keys=[lease_key, completion_key],
                args=[token, self._lease_ttl_ms],
            )
        except RedisError as exc:
            raise BackgroundJobCoordinationUnavailable from exc

        status_code = cast(int, result)
        if status_code == 2:
            return BackgroundJobClaim(BackgroundJobClaimStatus.ALREADY_COMPLETED)
        if status_code == 0:
            return BackgroundJobClaim(BackgroundJobClaimStatus.ALREADY_RUNNING)
        if status_code != 1:
            raise BackgroundJobCoordinationUnavailable

        lease: BackgroundJobLease = _RedisBackgroundJobLease(
            lease_key=lease_key,
            completion_key=completion_key,
            token=token,
            lease_ttl_ms=self._lease_ttl_ms,
            completion_ttl_ms=self._completion_ttl_ms,
            renew_interval_seconds=self._renew_interval_seconds,
            renew_script=self._renew_script,
            complete_script=self._complete_script,
            release_script=self._release_script,
        )
        return BackgroundJobClaim(BackgroundJobClaimStatus.ACQUIRED, lease)

    def _keys(self, job_name: str, scheduled_date: date) -> tuple[str, str]:
        run_key = f"{job_name}:{scheduled_date.isoformat()}"
        return (
            f"{self._key_prefix}:lease:{run_key}",
            f"{self._key_prefix}:completed:{run_key}",
        )


class _RedisBackgroundJobLease:
    def __init__(
        self,
        lease_key: str,
        completion_key: str,
        token: str,
        lease_ttl_ms: int,
        completion_ttl_ms: int,
        renew_interval_seconds: float,
        renew_script: AsyncScript,
        complete_script: AsyncScript,
        release_script: AsyncScript,
    ) -> None:
        self._lease_key = lease_key
        self._completion_key = completion_key
        self._token = token
        self._lease_ttl_ms = lease_ttl_ms
        self._completion_ttl_ms = completion_ttl_ms
        self._renew_interval_seconds = renew_interval_seconds
        self._renew_script = renew_script
        self._complete_script = complete_script
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
                keys=[self._lease_key],
                args=[self._token, self._lease_ttl_ms],
            )
        except RedisError as exc:
            raise BackgroundJobCoordinationUnavailable from exc
        return bool(cast(int, result))

    async def complete(self) -> None:
        if self._released:
            raise BackgroundJobLeaseLost
        try:
            result = await self._complete_script(
                keys=[self._lease_key, self._completion_key],
                args=[self._token, self._completion_ttl_ms],
            )
        except RedisError as exc:
            raise BackgroundJobCoordinationUnavailable from exc
        if not cast(int, result):
            raise BackgroundJobLeaseLost
        self._released = True

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            await self._release_script(
                keys=[self._lease_key],
                args=[self._token],
            )
        except RedisError as exc:
            raise BackgroundJobCoordinationUnavailable from exc
