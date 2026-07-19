from datetime import datetime
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class AgentRunUsageStatus(StrEnum):
    RESERVED = "reserved"
    CONSUMED = "consumed"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class AgentRunReservation:
    run_id: UUID
    user_id: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRunAllowance:
    user_id: UUID
    used: int
    limit: int
    remaining: int
