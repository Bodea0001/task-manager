from typing import Any, cast
from logging import getLogger

from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.types import AgentState as LangChainAgentState

from agents.agents import PlannerAgent
from agents.progress import dispatch_plan_progress
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.schemas.planning import AgentPlan


logger = getLogger(__name__)


class PlannerHistorySummarizationNode:
    """Compact persisted conversation history before it reaches the planner."""

    def __init__(
        self,
        middleware: SummarizationMiddleware[AgentResult, AgentContext],
    ) -> None:
        self._middleware = middleware

    async def __call__(
        self,
        state: AgentState,
        runtime: Runtime[AgentContext],
    ) -> dict[str, Any]:
        """Atomically replace old history only after a new summary is available."""
        update = await self._middleware.abefore_model(
            cast(LangChainAgentState[Any], state),
            runtime,
        )
        if _summary_generation_failed(update):
            logger.warning(
                "event=agent_history_summarization_completed outcome=error action=preserve_history",
                extra={
                    "event": "agent_history_summarization_completed",
                    "outcome": "error",
                    "action": "preserve_history",
                },
            )
            return {}

        return update or {}


class PlannerNode:
    """LangGraph node adapter around PlannerAgent."""

    def __init__(self, planner: PlannerAgent) -> None:
        self._planner = planner

    async def __call__(
        self, state: AgentState, config: RunnableConfig
    ) -> dict[str, AgentPlan | dict[str, AgentResult]]:
        """Create a plan and atomically initialize its execution state.

        Step results belong only to the plan that produced them. Clearing
        previous results together with installing the new plan prevents the
        executor from associating stale results with steps in the new plan.
        """
        plan = await self._planner.create_plan(state.get("messages", ()), config=config)
        await dispatch_plan_progress(plan, config)
        return {
            "plan": plan,
            "step_results": {},
        }


def _summary_generation_failed(update: dict[str, Any] | None) -> bool:
    if update is None:
        return False

    for message in update.get("messages", ()):
        if not isinstance(message, HumanMessage):
            continue
        if message.additional_kwargs.get("lc_source") != "summarization":
            continue

        content = message.content if isinstance(message.content, str) else str(message.content)
        summary = content.partition("\n\n")[2].strip()
        return not summary or summary.startswith("Error generating summary:")

    return False
