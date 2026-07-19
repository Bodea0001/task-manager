from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import NoResultFound

import exceptions as app_exc
from adapters.repository import SQLAlchemyRepository
from domain.value_objects.agent_usage import (
    AgentRunAllowance,
    AgentRunReservation,
    AgentRunUsageStatus,
)
from models.agent_usage import UserAgentRunUsage
from models.users import UserEmailVerification


class AgentUsageRepository(SQLAlchemyRepository):
    """Persist atomic quota reservations and their final outcome."""

    async def reserve(
        self,
        run_id: UUID,
        user_id: UUID,
        unverified_limit: int,
        verified_limit: int,
        now: datetime,
        expires_at: datetime,
    ) -> AgentRunReservation:
        try:
            verified_at = await self._lock_verification_state(user_id)
        except NoResultFound:
            raise app_exc.UserNotFound from None

        limit = verified_limit if verified_at is not None else unverified_limit
        active_usage = self._active_usage_count(user_id, now)
        candidate = select(
            literal(run_id),
            literal(user_id),
            literal(AgentRunUsageStatus.RESERVED.value),
            literal(expires_at),
        ).where(active_usage < limit)
        stmt = (
            insert(UserAgentRunUsage)
            .from_select(
                [
                    UserAgentRunUsage.run_id,
                    UserAgentRunUsage.user_id,
                    UserAgentRunUsage.status,
                    UserAgentRunUsage.reservation_expires_at,
                ],
                candidate,
            )
            .on_conflict_do_nothing(index_elements=[UserAgentRunUsage.run_id])
            .returning(UserAgentRunUsage.run_id)
        )
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return AgentRunReservation(run_id=run_id, user_id=user_id, expires_at=expires_at)

        existing = await self._get_existing_reservation(run_id, user_id)
        if existing is not None:
            return existing

        used = await self._get_active_usage_count(user_id, now)
        raise app_exc.AgentQuotaExhausted(used=used, limit=limit)

    async def consume(self, run_id: UUID, user_id: UUID, now: datetime) -> None:
        await self._finish(
            run_id,
            user_id,
            status=AgentRunUsageStatus.CONSUMED,
            now=now,
        )

    async def release(self, run_id: UUID, user_id: UUID, now: datetime) -> None:
        await self._finish(
            run_id,
            user_id,
            status=AgentRunUsageStatus.RELEASED,
            now=now,
        )

    async def get_allowance(
        self,
        user_id: UUID,
        unverified_limit: int,
        verified_limit: int,
        now: datetime,
    ) -> AgentRunAllowance:
        stmt = select(
            UserEmailVerification.verified_at,
            self._active_usage_count(user_id, now).label("used"),
        ).where(UserEmailVerification.user_id == user_id)
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise app_exc.UserNotFound
        limit = verified_limit if row.verified_at is not None else unverified_limit
        return AgentRunAllowance(
            user_id=user_id,
            used=row.used,
            limit=limit,
            remaining=max(limit - row.used, 0),
        )

    async def _lock_verification_state(self, user_id: UUID) -> datetime | None:
        stmt = (
            select(UserEmailVerification.verified_at)
            .where(UserEmailVerification.user_id == user_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_existing_reservation(
        self,
        run_id: UUID,
        user_id: UUID,
    ) -> AgentRunReservation | None:
        stmt = select(UserAgentRunUsage).where(
            UserAgentRunUsage.run_id == run_id,
            UserAgentRunUsage.user_id == user_id,
            UserAgentRunUsage.status.in_(
                (
                    AgentRunUsageStatus.RESERVED,
                    AgentRunUsageStatus.CONSUMED,
                )
            ),
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return AgentRunReservation(
            run_id=model.run_id,
            user_id=model.user_id,
            expires_at=model.reservation_expires_at,
        )

    def _active_usage_count(self, user_id: UUID, now: datetime):
        return (
            select(func.count())
            .select_from(UserAgentRunUsage)
            .where(
                UserAgentRunUsage.user_id == user_id,
                or_(
                    UserAgentRunUsage.status == AgentRunUsageStatus.CONSUMED,
                    and_(
                        UserAgentRunUsage.status == AgentRunUsageStatus.RESERVED,
                        UserAgentRunUsage.reservation_expires_at > now,
                    ),
                ),
            )
            .scalar_subquery()
        )

    async def _get_active_usage_count(self, user_id: UUID, now: datetime) -> int:
        result = await self.session.execute(select(self._active_usage_count(user_id, now)))
        return result.scalar_one()

    async def _finish(
        self,
        run_id: UUID,
        user_id: UUID,
        *,
        status: AgentRunUsageStatus,
        now: datetime,
    ) -> None:
        stmt = (
            update(UserAgentRunUsage)
            .values(status=status, finished_at=now)
            .where(
                UserAgentRunUsage.run_id == run_id,
                UserAgentRunUsage.user_id == user_id,
                UserAgentRunUsage.status == AgentRunUsageStatus.RESERVED,
            )
        )
        await self.session.execute(stmt)
