import asyncio
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Coroutine, Protocol, TypeVar


T = TypeVar("T")


class BackgroundJobCoordinationUnavailable(Exception):
    """Raised when execution ownership cannot be coordinated safely."""


class BackgroundJobLeaseLost(BackgroundJobCoordinationUnavailable):
    """Raised when a running job no longer owns its execution lease."""


class BackgroundJobClaimStatus(StrEnum):
    ACQUIRED = "acquired"
    ALREADY_RUNNING = "already_running"
    ALREADY_COMPLETED = "already_completed"


class BackgroundJobLease(Protocol):
    @property
    def renew_interval_seconds(self) -> float:
        """Return how often ownership should be renewed."""
        ...

    async def renew(self) -> bool:
        """Renew ownership if this execution still owns the lease."""
        ...

    async def complete(self) -> None:
        """Atomically mark the run complete and release ownership."""
        ...

    async def release(self) -> None:
        """Release ownership without marking the run complete."""
        ...


@dataclass(frozen=True, slots=True)
class BackgroundJobClaim:
    status: BackgroundJobClaimStatus
    lease: BackgroundJobLease | None = None


class BackgroundJobCoordinator(Protocol):
    async def claim(self, job_name: str, scheduled_date: date) -> BackgroundJobClaim:
        """Claim one date-scoped execution or report why it should be skipped."""
        ...


async def run_with_lease(
    lease: BackgroundJobLease,
    operation: Coroutine[Any, Any, T],
) -> T:
    """Run an operation while renewing ownership and complete it atomically."""
    operation_task = asyncio.create_task(operation)
    renewal_task = asyncio.create_task(_renew_lease(lease))
    completed = False
    primary_error: BaseException | None = None
    try:
        done, _ = await asyncio.wait(
            (operation_task, renewal_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if renewal_task in done:
            await renewal_task
            raise RuntimeError("Background job lease renewal stopped unexpectedly")

        result = await operation_task
        await lease.complete()
        completed = True
        return result
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        for task in (operation_task, renewal_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(operation_task, renewal_task, return_exceptions=True)
        if not completed:
            try:
                await lease.release()
            except BaseException as release_error:
                if primary_error is None:
                    raise
                primary_error.add_note(f"Background lease release also failed: {release_error!r}")


async def _renew_lease(lease: BackgroundJobLease) -> None:
    while True:
        await asyncio.sleep(lease.renew_interval_seconds)
        if not await lease.renew():
            raise BackgroundJobLeaseLost
