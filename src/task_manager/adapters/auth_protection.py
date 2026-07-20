from hashlib import sha256
from typing import cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from redis.exceptions import RedisError

import exceptions as app_exc
from config import AuthProtectionConfig
from presentation.auth_protection import RateLimitDecision, RegistrationPermit


_RATE_LIMIT_SCRIPT = """
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local count = tonumber(redis.call('GET', KEYS[1]) or '0')

if count >= limit then
    local retry_after = math.max(1, math.ceil(redis.call('PTTL', KEYS[1]) / 1000))
    return {0, retry_after}
end

count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], window_ms)
end
return {1, 0}
"""

_RESERVE_REGISTRATION_SCRIPT = """
local current_time = redis.call('TIME')
local now_ms = current_time[1] * 1000 + math.floor(current_time[2] / 1000)
local reservation_ttl_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now_ms)
local completed = tonumber(redis.call('GET', KEYS[1]) or '0')
local pending = redis.call('ZCARD', KEYS[2])
if completed + pending >= limit then
    return 0
end

redis.call('ZADD', KEYS[2], now_ms + reservation_ttl_ms, ARGV[3])
redis.call('PEXPIRE', KEYS[2], reservation_ttl_ms)
return 1
"""

_CONFIRM_REGISTRATION_SCRIPT = """
if redis.call('ZREM', KEYS[2], ARGV[1]) == 1 then
    redis.call('INCR', KEYS[1])
    return 1
end
return 0
"""

_RELEASE_REGISTRATION_SCRIPT = """
return redis.call('ZREM', KEYS[1], ARGV[1])
"""


class RedisAnonymousAuthProtection:
    """Apply distributed auth limits through atomic Redis-compatible scripts."""

    def __init__(self, client: Redis, config: AuthProtectionConfig) -> None:
        self._key_prefix = config.key_prefix
        self._registration_attempt_limit = config.registration_attempt_limit
        self._login_attempt_limit = config.login_attempt_limit
        self._attempt_window_ms = config.attempt_window_seconds * 1_000
        self._successful_registration_limit = config.successful_registration_limit
        self._reservation_ttl_ms = config.registration_reservation_ttl_seconds * 1_000
        self._rate_limit_script = client.register_script(_RATE_LIMIT_SCRIPT)
        self._reserve_script = client.register_script(_RESERVE_REGISTRATION_SCRIPT)
        self._confirm_script = client.register_script(_CONFIRM_REGISTRATION_SCRIPT)
        self._release_script = client.register_script(_RELEASE_REGISTRATION_SCRIPT)

    async def check_registration_attempt(self, client_address: str) -> RateLimitDecision:
        return await self._check_rate_limit(
            operation="registration",
            client_address=client_address,
            limit=self._registration_attempt_limit,
        )

    async def check_login_attempt(self, client_address: str) -> RateLimitDecision:
        return await self._check_rate_limit(
            operation="login",
            client_address=client_address,
            limit=self._login_attempt_limit,
        )

    async def reserve_registration(self, client_address: str) -> RegistrationPermit | None:
        client_key = self._client_key(client_address)
        completed_key = f"{self._key_prefix}:registration:{{{client_key}}}:completed"
        pending_key = f"{self._key_prefix}:registration:{{{client_key}}}:pending"
        token = uuid4().hex
        try:
            result = await self._reserve_script(
                keys=[completed_key, pending_key],
                args=[
                    self._reservation_ttl_ms,
                    self._successful_registration_limit,
                    token,
                ],
            )
        except RedisError as exc:
            raise app_exc.AuthProtectionUnavailable from exc

        if not cast(int, result):
            return None
        return _RedisRegistrationPermit(
            completed_key=completed_key,
            pending_key=pending_key,
            token=token,
            confirm_script=self._confirm_script,
            release_script=self._release_script,
        )

    async def _check_rate_limit(
        self,
        *,
        operation: str,
        client_address: str,
        limit: int,
    ) -> RateLimitDecision:
        client_key = self._client_key(client_address)
        key = f"{self._key_prefix}:rate:{operation}:{{{client_key}}}"
        try:
            result = await self._rate_limit_script(
                keys=[key],
                args=[self._attempt_window_ms, limit],
            )
        except RedisError as exc:
            raise app_exc.AuthProtectionUnavailable from exc

        allowed, retry_after_seconds = cast(list[int], result)
        return RateLimitDecision(
            allowed=bool(allowed),
            retry_after_seconds=None if allowed else retry_after_seconds,
        )

    @staticmethod
    def _client_key(client_address: str) -> str:
        return sha256(client_address.encode("ascii")).hexdigest()


class _RedisRegistrationPermit:
    def __init__(
        self,
        *,
        completed_key: str,
        pending_key: str,
        token: str,
        confirm_script: AsyncScript,
        release_script: AsyncScript,
    ) -> None:
        self._completed_key = completed_key
        self._pending_key = pending_key
        self._token = token
        self._confirm_script = confirm_script
        self._release_script = release_script
        self._finished = False

    async def confirm(self) -> None:
        if self._finished:
            return
        try:
            result = await self._confirm_script(
                keys=[self._completed_key, self._pending_key],
                args=[self._token],
            )
        except RedisError as exc:
            raise app_exc.AuthProtectionUnavailable from exc
        if not cast(int, result):
            raise app_exc.AuthProtectionUnavailable
        self._finished = True

    async def release(self) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            await self._release_script(
                keys=[self._pending_key],
                args=[self._token],
            )
        except RedisError as exc:
            raise app_exc.AuthProtectionUnavailable from exc
