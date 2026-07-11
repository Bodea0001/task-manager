from typing import Any, cast
from collections.abc import Mapping

from langgraph.runtime import Runtime
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from agents.progress import dispatch_plan_progress
from agents.agents import ResponderAgent
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult, AgentStatus
from agents.schemas.context import AgentContext
from agents.schemas.planning import (
    AgentPlan,
    CompiledSubAgent,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
)


class PlanStepStartNode:
    """Mark the next pending plan step as in progress before it is executed."""

    async def __call__(
        self,
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, AgentPlan]:
        plan = state.get("plan")
        step = _next_pending_step(plan)
        if plan is None or step is None:
            return {}

        updated_plan = _with_step_status(plan, step.step_id, PlanStepStatus.IN_PROGRESS)
        await dispatch_plan_progress(updated_plan, config)
        return {"plan": updated_plan}


class PlanExecutorNode:
    """Execute the active plan step and persist its result and final status."""

    def __init__(self, subagents: Mapping[str, CompiledSubAgent]) -> None:
        self._subagents = dict(subagents)

    async def __call__(
        self,
        state: AgentState,
        config: RunnableConfig | None = None,
        *,
        runtime: Runtime[AgentContext],
    ) -> dict[str, Any]:
        plan = state.get("plan")
        step_results = dict(state.get("step_results", {}))
        step = _in_progress_step(plan)
        if plan is None or step is None:
            return {"step_results": step_results}

        subagent = self._subagents.get(step.agent_id)
        if subagent is None:
            result = AgentResult(
                status=AgentStatus.REJECTED,
                message=f"No subagent is registered for plan step {step.step_id}.",
            )
        else:
            subagent_result = await subagent.runnable.ainvoke(
                {"messages": [HumanMessage(content=_step_message(step))]},
                config=_subagent_config(step=step, subagent=subagent),
                context=runtime.context,
            )
            result = _to_agent_result(subagent_result)

        step_results[step.step_id] = result
        updated_plan = _with_step_status(plan, step.step_id, _result_step_status(result))
        await dispatch_plan_progress(updated_plan, config or {})
        return {
            "plan": updated_plan,
            "step_results": step_results,
        }


class PlanResponderNode:
    """Convert a plan and step results into the graph's final structured response."""

    def __init__(self, responder: ResponderAgent) -> None:
        self._responder = responder

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await self._responder.respond(
            state.get("plan"),
            state.get("step_results", {}),
            config=config,
        )
        return {
            "structured_response": result,
            "messages": [AIMessage(content=result.message)],
            "plan": None,
            "step_results": {},
        }


def plan_is_executable(state: AgentState) -> str:
    plan = state.get("plan")
    if plan is not None and plan.status == PlanStatus.EXECUTABLE:
        return "execute"

    return "respond"


def plan_has_more_steps(state: AgentState) -> str:
    if _next_pending_step(state.get("plan")) is not None:
        return "start"

    return "respond"


def _next_pending_step(plan: AgentPlan | None) -> PlanStep | None:
    if plan is None or plan.status != PlanStatus.EXECUTABLE:
        return None

    for step in plan.steps:
        if step.status == PlanStepStatus.PENDING:
            return step

    return None


def _in_progress_step(plan: AgentPlan | None) -> PlanStep | None:
    if plan is None or plan.status != PlanStatus.EXECUTABLE:
        return None

    for step in plan.steps:
        if step.status == PlanStepStatus.IN_PROGRESS:
            return step

    return None


def _with_step_status(
    plan: AgentPlan,
    step_id: str,
    status: PlanStepStatus,
) -> AgentPlan:
    steps = [
        step.model_copy(update={"status": status}) if step.step_id == step_id else step
        for step in plan.steps
    ]
    return plan.model_copy(update={"steps": steps})


def _result_step_status(result: AgentResult) -> PlanStepStatus:
    if result.status == AgentStatus.REJECTED:
        return PlanStepStatus.FAILED

    return PlanStepStatus.COMPLETED


def _step_message(step: PlanStep) -> str:
    subtasks = "\n".join(f"- {subtask}" for subtask in step.subtasks)
    if subtasks:
        return f"Assigned step:\n{step.instruction}\n\nSubtasks:\n{subtasks}"

    return f"Assigned step:\n{step.instruction}"


def _subagent_config(
    *,
    step: PlanStep,
    subagent: CompiledSubAgent,
) -> RunnableConfig:
    return cast(
        RunnableConfig,
        {
            "metadata": {
                "plan_step_id": step.step_id,
                "plan_step_title": step.title,
                "subagent_id": subagent.agent_id,
            },
            "run_name": subagent.agent_id,
        },
    )


def _to_agent_result(result: Any) -> AgentResult:
    if isinstance(result, dict):
        structured_response = result.get("structured_response")
        if isinstance(structured_response, AgentResult):
            return structured_response

        message = _last_ai_message(result)
        if message:
            return AgentResult(status=AgentStatus.COMPLETED, message=message)

    return AgentResult(status=AgentStatus.COMPLETED, message="Done.")


def _last_ai_message(result: dict[str, Any]) -> str:
    for message in reversed(result.get("messages") or []):
        if isinstance(message, AIMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)

    return ""
