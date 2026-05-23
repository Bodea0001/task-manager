from uuid import UUID
from typing import Any

from sqlalchemy import select, insert

from models.audit import AuditEvent as AuditEventModel
from domain.value_objects.audit import AuditEvent, AuditEntityType, AuditEventType
from adapters.repository import SQLAlchemyRepository


class AuditRepository(SQLAlchemyRepository):
    async def add_event(
        self,
        *,
        actor_user_id: UUID,
        entity_type: AuditEntityType,
        entity_id: UUID,
        event_type: AuditEventType,
        data: dict[str, Any] | None = None,
    ) -> None:
        stmt = insert(AuditEventModel).values(
            actor_user_id=actor_user_id,
            entity_type=entity_type.value,
            entity_id=entity_id,
            event_type=event_type.value,
            data=data or {},
        )

        await self.session.execute(stmt)

    async def add_events(
        self,
        events: list[dict[str, Any]],
    ) -> None:
        if not events:
            return

        stmt = insert(AuditEventModel).values(events)

        await self.session.execute(stmt)

    async def get_events(
        self,
        *,
        entity_type: AuditEntityType,
        entity_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEventModel)
            .where(
                AuditEventModel.entity_type == entity_type.value,
                AuditEventModel.entity_id == entity_id,
            )
            .order_by(AuditEventModel.occurred_at, AuditEventModel.event_id)
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return [self._model_to_event(model) for model in result.scalars().all()]

    @staticmethod
    def _model_to_event(model: AuditEventModel) -> AuditEvent:
        return AuditEvent(
            event_id=model.event_id,
            actor_user_id=model.actor_user_id,
            entity_type=AuditEntityType(model.entity_type),
            entity_id=model.entity_id,
            event_type=AuditEventType(model.event_type),
            data=model.data,
            occurred_at=model.occurred_at,
        )
