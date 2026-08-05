from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from adapters.unitofwork import SQLAlchemyUnitOfWork
from config import AgentUsageConfig, settings
from dto.agent_usage import SetAgentAccessData
from domain.value_objects.agent_usage import AgentAccess, AgentRunAllowance, AgentRunReservation


class AgentUsageService:
    """Reserve and finalize user-visible agent request quota units."""

    def __init__(
        self,
        uow: SQLAlchemyUnitOfWork,
        config: AgentUsageConfig | None = None,
    ) -> None:
        self.uow = uow
        self.config = config or settings.agent_usage

    async def create_reservation(self, user_id: UUID) -> AgentRunReservation:
        """Create an application-owned agent attempt and reserve its quota unit."""
        return await self.reserve(uuid7(), user_id)

    async def reserve(self, run_id: UUID, user_id: UUID) -> AgentRunReservation:
        now = datetime.now(UTC)
        async with self.uow() as uow:
            return await uow.agent_usage.reserve(
                run_id=run_id,
                user_id=user_id,
                unverified_limit=self.config.unverified_run_limit,
                verified_limit=self.config.verified_run_limit,
                now=now,
                expires_at=now + timedelta(seconds=self.config.reservation_ttl_seconds),
            )

    async def consume(self, run_id: UUID, user_id: UUID) -> None:
        async with self.uow() as uow:
            await uow.agent_usage.consume(run_id, user_id, datetime.now(UTC))

    async def release(self, run_id: UUID, user_id: UUID) -> None:
        async with self.uow() as uow:
            await uow.agent_usage.release(run_id, user_id, datetime.now(UTC))

    async def get_allowance(self, user_id: UUID) -> AgentRunAllowance:
        async with self.uow(read_only=True) as uow:
            return await uow.agent_usage.get_allowance(
                user_id=user_id,
                unverified_limit=self.config.unverified_run_limit,
                verified_limit=self.config.verified_run_limit,
                now=datetime.now(UTC),
            )

    async def set_access_level(self, data: SetAgentAccessData) -> AgentAccess:
        """Set agent access for a user through a trusted administrative adapter."""
        async with self.uow() as uow:
            return await uow.agent_usage.set_access_level(data.email, data.access_level)
