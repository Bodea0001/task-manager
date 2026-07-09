from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(StrEnum):
    """Final task-agent execution status."""

    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AgentStatus = Field(
        description="Structured outcome of the agent run.",
    )
    message: str = Field(
        description="User-facing answer produced by the agent.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured data used by callers for follow-up flows.",
    )
