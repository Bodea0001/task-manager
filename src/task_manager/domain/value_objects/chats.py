from uuid import UUID
from datetime import datetime
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chat:
    chat_id: UUID
    creator_id: UUID
    is_active: bool
    created_at: datetime
