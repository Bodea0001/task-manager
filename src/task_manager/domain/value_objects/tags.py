from uuid import UUID
from datetime import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class Tag:
    tag_id: UUID
    name: str
    created_at: datetime
