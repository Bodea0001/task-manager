import json
from typing import Any
from logging import getLogger
from functools import cached_property
from collections.abc import Sequence

from pydantic import ValidationError
from langchain_core.messages import SystemMessage, AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel

from agents.prompts import PLANNER_PROMPT, PLANNER_REPAIR_PROMPT
from agents.schemas.planning import AgentPlan, CompiledSubAgent, PlanStep, PlannerOutput


logger = getLogger(__name__)


class PlannerResultError(ValueError):
    """Raised when the planner model returns an invalid plan payload."""


class PlannerAgent:
    """Create structured execution plans for specialized task-manager agents."""

    def __init__(
        self,
        model: BaseChatModel,
        subagents: Sequence[CompiledSubAgent],
    ) -> None:
        if not subagents:
            msg = "PlannerAgent requires at least one available subagent."
            raise ValueError(msg)

        self._model = model
        self._subagents = tuple(subagents)

    async def create_plan(
        self, messages: Sequence[BaseMessage], config: RunnableConfig
    ) -> AgentPlan:
        """Ask the planner model for a JSON plan and validate it."""
        request_messages = [SystemMessage(self._system_prompt), *messages]
        result = await self._model.ainvoke(request_messages, config=config)
        try:
            return _parse_planner_result(
                result,
                allowed_agent_ids=self._allowed_agent_ids,
            )
        except PlannerResultError as exc:
            logger.warning("Planner returned an invalid result; retrying once: %s", exc)

        retry_result = await self._model.ainvoke(
            [
                *request_messages,
                HumanMessage(content=PLANNER_REPAIR_PROMPT),
            ],
            config=config,
        )
        try:
            return _parse_planner_result(
                retry_result,
                allowed_agent_ids=self._allowed_agent_ids,
            )
        except PlannerResultError as exc:
            msg = "Planner returned an invalid result after retry."
            raise PlannerResultError(msg) from exc

    @cached_property
    def _system_prompt(self) -> str:
        return PLANNER_PROMPT.format(subagents=_format_subagents(self._subagents))

    @cached_property
    def _allowed_agent_ids(self) -> set[str]:
        return {subagent.agent_id for subagent in self._subagents}


def _parse_planner_result(result: Any, allowed_agent_ids: set[str] | None = None) -> AgentPlan:
    """Parse and validate the planner model response."""
    content = result.content if isinstance(result, AIMessage) else result
    if not isinstance(content, str):
        msg = "Planner result must be a JSON string."
        raise PlannerResultError(msg)

    try:
        payload = json.loads(_strip_json_markdown(content))
    except json.JSONDecodeError as exc:
        msg = "Planner result is not valid JSON."
        raise PlannerResultError(msg) from exc

    try:
        output = PlannerOutput.model_validate(payload)
    except ValidationError as exc:
        msg = "Planner result does not match the plan schema."
        raise PlannerResultError(msg) from exc

    if allowed_agent_ids is not None:
        used_agent_ids = {step.agent_id for step in output.steps}
        unknown_agent_ids = used_agent_ids - allowed_agent_ids
        if unknown_agent_ids:
            msg = f"Planner selected unknown subagent ids: {unknown_agent_ids}."
            raise PlannerResultError(msg)

    return _build_agent_plan(output)


def _build_agent_plan(output: PlannerOutput) -> AgentPlan:
    steps = [
        PlanStep(
            step_id=f"step_{index}",
            title=step.title,
            agent_id=step.agent_id,
            instruction=step.instruction,
            subtasks=step.subtasks,
        )
        for index, step in enumerate(output.steps, start=1)
    ]
    return AgentPlan(
        status=output.status,
        objective=output.objective,
        steps=steps,
        clarification_question=output.clarification_question,
    )


def _format_subagents(subagents: Sequence[CompiledSubAgent]) -> str:
    lines = [
        f"- {subagent.agent_id}: {subagent.display_name} - {subagent.description}"
        for subagent in subagents
    ]
    return "\n".join(lines)


def _strip_json_markdown(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
