from uuid import UUID
from enum import StrEnum
from datetime import datetime
from dataclasses import field, dataclass
from typing import Any


class AuditEntityType(StrEnum):
    TASK = "task"
    TAG = "tag"


class AuditEventType(StrEnum):
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_DELETED = "task.deleted"
    TASK_TAG_ADDED = "task.tag_added"
    TASK_TAG_REMOVED = "task.tag_removed"
    TASK_SCHEDULE_DELETED = "task.schedule_deleted"
    TAG_CREATED = "tag.created"
    TAG_UPDATED = "tag.updated"
    TAG_DELETED = "tag.deleted"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: UUID
    actor_user_id: UUID
    entity_type: AuditEntityType
    entity_id: UUID
    event_type: AuditEventType
    occurred_at: datetime
    data: dict[str, Any] = field(default_factory=dict)
