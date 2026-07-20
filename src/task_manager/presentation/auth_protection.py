from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Result of one atomic short-window request-limit check."""

    allowed: bool
    retry_after_seconds: int | None = None


class RegistrationPermit(Protocol):
    """A temporary registration slot that can be confirmed or released."""

    async def confirm(self) -> None: ...

    async def release(self) -> None: ...


class AnonymousAuthProtection(Protocol):
    """Protect anonymous authentication operations for one client address."""

    async def check_registration_attempt(self, client_address: str) -> RateLimitDecision: ...

    async def check_login_attempt(self, client_address: str) -> RateLimitDecision: ...

    async def reserve_registration(self, client_address: str) -> RegistrationPermit | None: ...
