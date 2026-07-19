from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import NoResultFound

import exceptions as app_exc
from adapters.repository import SQLAlchemyRepository
from domain.value_objects.agent_usage import (
    AgentAccess,
    AgentAccessLevel,
    AgentRunAllowance,
    AgentRunReservation,
    AgentRunUsageStatus,
)
from models.agent_usage import UserAgentAccess, UserAgentRunUsage
from models.users import User, UserEmailVerification


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
            verified_at, access_level = await self._lock_access_state(user_id)
        except NoResultFound:
            raise app_exc.UserNotFound from None

        limit = verified_limit if verified_at is not None else unverified_limit
        candidate = select(
            literal(run_id),
            literal(user_id),
            literal(AgentRunUsageStatus.RESERVED.value),
            literal(expires_at),
        )
        if access_level is AgentAccessLevel.LIMITED:
            candidate = candidate.where(self._active_usage_count(user_id, now) < limit)
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

        if access_level is AgentAccessLevel.UNMETERED:
            raise RuntimeError("Unmetered agent usage reservation could not be persisted")

        used = await self._get_active_usage_count(user_id, now)
        raise app_exc.AgentQuotaExhausted(used=used, limit=limit)

    async def set_access_level(
        self,
        email: str,
        access_level: AgentAccessLevel,
    ) -> AgentAccess:
        stmt = (
            update(UserAgentAccess)
            .values(access_level=access_level)
            .where(
                UserAgentAccess.user_id
                == select(User.user_id).where(User.email == email).scalar_subquery()
            )
            .returning(UserAgentAccess.user_id, UserAgentAccess.access_level)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise app_exc.UserNotFound
        return AgentAccess(user_id=row.user_id, access_level=row.access_level)

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
        stmt = (
            select(
                UserEmailVerification.verified_at,
                UserAgentAccess.access_level,
                self._active_usage_count(user_id, now).label("used"),
            )
            .join(
                UserAgentAccess,
                UserAgentAccess.user_id == UserEmailVerification.user_id,
            )
            .where(UserEmailVerification.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise app_exc.UserNotFound
        if row.access_level is AgentAccessLevel.UNMETERED:
            limit = None
            remaining = None
        else:
            limit = verified_limit if row.verified_at is not None else unverified_limit
            remaining = max(limit - row.used, 0)
        return AgentRunAllowance(
            user_id=user_id,
            used=row.used,
            access_level=row.access_level,
            limit=limit,
            remaining=remaining,
        )

    async def _lock_access_state(
        self,
        user_id: UUID,
    ) -> tuple[datetime | None, AgentAccessLevel]:
        stmt = (
            select(
                UserEmailVerification.verified_at,
                UserAgentAccess.access_level,
            )
            .join(
                UserAgentAccess,
                UserAgentAccess.user_id == UserEmailVerification.user_id,
            )
            .where(UserEmailVerification.user_id == user_id)
            .with_for_update(of=(UserEmailVerification, UserAgentAccess))
        )
        result = await self.session.execute(stmt)
        row = result.one()
        return row.verified_at, row.access_level

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
