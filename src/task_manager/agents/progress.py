from uuid import UUID
from typing import Any
from logging import getLogger
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict
from langchain_core.callbacks import AsyncCallbackHandler, adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from agents.schemas.planning import AgentPlan, PlanStatus, PlanStepStatus


logger = getLogger(__name__)

PLAN_PROGRESS_EVENT_NAME = "agent_plan_progress"


class PlanStepProgress(BaseModel):
    """User-visible execution state for one plan step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    title: str
    status: PlanStepStatus


class AgentPlanProgressEvent(BaseModel):
    """Complete user-visible plan snapshot used to update progress UI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: str
    status: PlanStatus
    steps: tuple[PlanStepProgress, ...]

    @classmethod
    def from_plan(cls, plan: AgentPlan) -> "AgentPlanProgressEvent":
        """Build a UI-safe snapshot without exposing agent instructions or internals."""
        return cls(
            objective=plan.objective,
            status=plan.status,
            steps=tuple(
                PlanStepProgress(
                    step_id=step.step_id,
                    title=step.title,
                    status=step.status,
                )
                for step in plan.steps
            ),
        )


AgentPlanProgressCallback = Callable[[AgentPlanProgressEvent], Awaitable[None]]


async def dispatch_plan_progress(plan: AgentPlan, config: RunnableConfig) -> None:
    """Dispatch a full plan snapshot when progress callbacks are configured."""
    if not config.get("callbacks"):
        return

    event = AgentPlanProgressEvent.from_plan(plan)
    await adispatch_custom_event(
        PLAN_PROGRESS_EVENT_NAME,
        event.model_dump(mode="json"),
        config=config,
    )


class AgentPlanProgressCallbackHandler(AsyncCallbackHandler):
    """Forward structured plan snapshots and ignore unrelated callback events."""

    def __init__(self, progress_callback: AgentPlanProgressCallback) -> None:
        self._progress_callback = progress_callback

    async def on_custom_event(
        self,
        name: str,
        data: Any,
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if name != PLAN_PROGRESS_EVENT_NAME:
            return

        try:
            event = AgentPlanProgressEvent.model_validate(data)
        except ValueError as exc:
            logger.warning(
                "event=agent_plan_progress_rejected run_id=%s outcome=ignored "
                "reason=invalid_event error_type=%s",
                run_id,
                type(exc).__name__,
                extra={
                    "event": "agent_plan_progress_rejected",
                    "run_id": str(run_id),
                    "outcome": "ignored",
                    "reason": "invalid_event",
                    "error_type": type(exc).__name__,
                },
            )
            return

        try:
            await self._progress_callback(event)
        except Exception as exc:
            logger.error(
                "event=agent_plan_progress_callback_completed run_id=%s outcome=error "
                "error_type=%s",
                run_id,
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
                extra={
                    "event": "agent_plan_progress_callback_completed",
                    "run_id": str(run_id),
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                },
            )
