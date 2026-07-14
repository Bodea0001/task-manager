from typing import Any
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.value_objects.audit import AuditEntityType, AuditEvent, AuditEventType


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    actor_user_id: UUID
    entity_type: AuditEntityType
    entity_id: UUID
    event_type: AuditEventType
    occurred_at: datetime
    data: dict[str, Any]

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            event_id=event.event_id,
            actor_user_id=event.actor_user_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            data=event.data,
        )


class AuditEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    events: tuple[AuditEventResponse, ...]

    @classmethod
    def from_domain(cls, events: list[AuditEvent]) -> "AuditEventListResponse":
        return cls(events=tuple(AuditEventResponse.from_domain(event) for event in events))
