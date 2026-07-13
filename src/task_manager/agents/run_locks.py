from typing import Protocol
from uuid import UUID


class AgentRunLease(Protocol):
    """Ownership claim for one active chat-bound agent run."""

    @property
    def renew_interval_seconds(self) -> float:
        """Return how often the lease should be renewed."""
        ...

    async def renew(self) -> bool:
        """Extend the lease only if this run still owns it."""
        ...

    async def release(self) -> None:
        """Release the lease only if this run still owns it."""
        ...


class AgentRunLockManager(Protocol):
    """Acquire distributed ownership of chat-bound agent execution."""

    async def acquire(self, chat_id: UUID) -> AgentRunLease | None:
        """Return a lease, or None when another run owns the chat."""
        ...
