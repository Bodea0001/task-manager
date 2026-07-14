from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from config import settings
from agents.progress import AgentPlanProgressEvent
from agents.schemas.planning import PlanStatus, PlanStepStatus
from agents.schemas.result import AgentResult, AgentStatus


class AgentRequest(BaseModel):
    """Natural-language request submitted to one chat session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=settings.agent.max_message_length)


class AgentPlanStepResponse(BaseModel):
    """User-visible progress for one plan step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    title: str
    status: PlanStepStatus


class AgentPlanResponse(BaseModel):
    """Complete plan snapshot sent whenever execution progress changes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str
    status: PlanStatus
    steps: tuple[AgentPlanStepResponse, ...]

    @classmethod
    def from_progress(cls, event: AgentPlanProgressEvent) -> "AgentPlanResponse":
        return cls(
            objective=event.objective,
            status=event.status,
            steps=tuple(
                AgentPlanStepResponse(
                    step_id=step.step_id,
                    title=step.title,
                    status=step.status,
                )
                for step in event.steps
            ),
        )


class AgentResultResponse(BaseModel):
    """Final structured outcome of an agent request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AgentStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_result(cls, result: AgentResult) -> "AgentResultResponse":
        return cls(status=result.status, message=result.message, data=result.data)


class AgentErrorResponse(BaseModel):
    """Safe terminal error emitted after an SSE response has started."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    request_id: str


class AgentHeartbeatResponse(BaseModel):
    """Empty keep-alive payload for an active agent stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)
