import json
from collections.abc import Mapping

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel

from agents.prompts import RESPONDER_PROMPT
from agents.schemas.result import AgentResult, AgentStatus
from agents.schemas.planning import AgentPlan, PlanStatus


class ResponderAgent:
    """Compose one final user-facing response from ordered plan outcomes."""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def respond(
        self,
        plan: AgentPlan | None,
        step_results: Mapping[str, AgentResult],
        config: RunnableConfig,
    ) -> AgentResult:
        """Synthesize completed step outcomes while keeping status and data deterministic."""
        early_result = _early_result(plan, step_results)
        if early_result is not None:
            return early_result

        assert plan is not None
        ordered_results = _ordered_results(plan, step_results)
        response = await self._model.ainvoke(
            [
                SystemMessage(content=RESPONDER_PROMPT),
                HumanMessage(content=_response_payload(plan, ordered_results)),
            ],
            config=config,
        )
        message = _response_text(response) or _fallback_message(ordered_results)
        return AgentResult(
            status=_combined_status([result for _, result in ordered_results]),
            message=message,
            data=_combined_data(ordered_results),
        )


def _early_result(
    plan: AgentPlan | None,
    step_results: Mapping[str, AgentResult],
) -> AgentResult | None:
    if plan is None:
        return AgentResult(
            status=AgentStatus.REJECTED,
            message="The request could not be planned.",
        )

    if plan.status == PlanStatus.NEEDS_CLARIFICATION:
        return AgentResult(
            status=AgentStatus.NEEDS_CLARIFICATION,
            message=plan.clarification_question or "Please clarify the request.",
        )

    if not plan.steps:
        return AgentResult(status=AgentStatus.REJECTED, message="The plan has no executable steps.")

    if not _ordered_results(plan, step_results):
        return AgentResult(status=AgentStatus.REJECTED, message="No plan steps were executed.")

    return None


def _ordered_results(
    plan: AgentPlan,
    step_results: Mapping[str, AgentResult],
) -> list[tuple[str, AgentResult]]:
    return [
        (step.step_id, result)
        for step in plan.steps
        if (result := step_results.get(step.step_id)) is not None
    ]


def _response_payload(
    plan: AgentPlan,
    ordered_results: list[tuple[str, AgentResult]],
) -> str:
    steps_by_id = {step.step_id: step for step in plan.steps}
    payload = {
        "objective": plan.objective,
        "outcomes": [
            {
                "title": steps_by_id[step_id].title,
                "status": result.status,
                "message": result.message,
            }
            for step_id, result in ordered_results
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _response_text(response: object) -> str:
    if not isinstance(response, AIMessage):
        return ""

    return str(response.text).strip()


def _fallback_message(ordered_results: list[tuple[str, AgentResult]]) -> str:
    return "\n".join(result.message for _, result in ordered_results)


def _combined_status(results: list[AgentResult]) -> AgentStatus:
    if any(result.status == AgentStatus.REJECTED for result in results):
        return AgentStatus.REJECTED

    if any(result.status == AgentStatus.NEEDS_CLARIFICATION for result in results):
        return AgentStatus.NEEDS_CLARIFICATION

    return AgentStatus.COMPLETED


def _combined_data(ordered_results: list[tuple[str, AgentResult]]) -> dict[str, object]:
    if len(ordered_results) == 1:
        return ordered_results[0][1].data

    step_data = {step_id: result.data for step_id, result in ordered_results if result.data}
    return {"step_results": step_data} if step_data else {}
