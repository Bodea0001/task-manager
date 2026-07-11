from typing import Self
from enum import StrEnum
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.types import AgentGraph


class PlanStatus(StrEnum):
    """Planner outcome before execution starts."""

    EXECUTABLE = "executable"
    NEEDS_CLARIFICATION = "needs_clarification"


class PlanStepStatus(StrEnum):
    """Execution status for a user-visible plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class CompiledSubAgent:
    """Initialized agent graph with planner-facing metadata."""

    agent_id: str
    display_name: str
    description: str
    runnable: AgentGraph


class PlanStepDraft(BaseModel):
    """Planner-produced step before code assigns execution metadata."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=80,
        description="Short user-visible step name shown while the plan is executing.",
    )
    agent_id: str = Field(
        min_length=1,
        max_length=80,
        description="Registered specialized agent id responsible for this step.",
    )
    instruction: str = Field(
        min_length=1,
        description="Self-contained instruction for the assigned specialized agent.",
    )
    subtasks: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Optional smaller actions that belong to this same step and agent.",
    )


class PlanStep(PlanStepDraft):
    """One executable unit assigned to a single specialized agent."""

    step_id: str = Field(
        min_length=1,
        max_length=64,
        description="Stable machine-readable step id assigned by application code.",
    )
    status: PlanStepStatus = Field(
        default=PlanStepStatus.PENDING,
        description="Current execution status. New plans should start with pending steps.",
    )


class PlannerOutput(BaseModel):
    """Validated model output before execution ids and statuses are assigned."""

    model_config = ConfigDict(extra="forbid")

    status: PlanStatus = Field(
        description="Whether the request is executable or needs more user context.",
    )
    objective: str = Field(
        min_length=1,
        description="Short normalized statement of the user's current objective.",
    )
    steps: list[PlanStepDraft] = Field(
        default_factory=list,
        max_length=8,
        description="Ordered executable steps. Empty only when clarification is required.",
    )
    clarification_question: str | None = Field(
        default=None,
        description="Question to ask the user when a safe plan cannot be created.",
    )

    @model_validator(mode="after")
    def validate_plan_shape(self) -> Self:
        if self.status == PlanStatus.EXECUTABLE and not self.steps:
            msg = "Executable plans must contain at least one step."
            raise ValueError(msg)

        if self.status == PlanStatus.NEEDS_CLARIFICATION and not self.clarification_question:
            msg = "Clarification plans must contain a clarification question."
            raise ValueError(msg)

        return self


class AgentPlan(BaseModel):
    """Structured plan consumed by the graph executor."""

    model_config = ConfigDict(extra="forbid")

    status: PlanStatus = Field(
        description="Whether the request is executable or needs more user context.",
    )
    objective: str = Field(
        min_length=1,
        description="Short normalized statement of the user's current objective.",
    )
    steps: list[PlanStep] = Field(
        default_factory=list,
        max_length=8,
        description="Ordered executable steps with code-assigned ids and statuses.",
    )
    clarification_question: str | None = Field(
        default=None,
        description="Question to ask the user when a safe plan cannot be created.",
    )

    @model_validator(mode="after")
    def validate_plan_shape(self) -> Self:
        if self.status == PlanStatus.EXECUTABLE and not self.steps:
            msg = "Executable plans must contain at least one step."
            raise ValueError(msg)

        if self.status == PlanStatus.NEEDS_CLARIFICATION and not self.clarification_question:
            msg = "Clarification plans must contain a clarification question."
            raise ValueError(msg)

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            msg = "Plan step ids must be unique."
            raise ValueError(msg)

        return self
