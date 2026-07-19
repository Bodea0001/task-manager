from typing import Any, cast
from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.prompts import TASK_RECURRENCE_RULE_AGENT_PROMPT
from agents.types import AgentGraph
from agents.tools.system import get_current_datetime
from agents.tools.tasks import (
    get_task_recurrence_rules,
    get_task_recurrence_template,
    add_task_recurrence_rule,
    update_task_recurrence_rule,
    stop_task_recurrence,
    list_task_recurrence_templates,
)
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.middlewares import (
    ApplicationErrorMiddleware,
    RepeatedToolCallGuardMiddleware,
)

_TOOLS = (
    get_current_datetime,
    list_task_recurrence_templates,
    get_task_recurrence_template,
    get_task_recurrence_rules,
    add_task_recurrence_rule,
    update_task_recurrence_rule,
    stop_task_recurrence,
)
_NON_MUTATING_TOOL_NAMES = {
    get_current_datetime.name,
    list_task_recurrence_templates.name,
    get_task_recurrence_template.name,
    get_task_recurrence_rules.name,
    AgentResult.__name__,
}

_MIDDLEWARES: Sequence[AgentMiddleware[Any, AgentContext, Any]] = (
    ApplicationErrorMiddleware(),
    ToolCallLimitMiddleware[AgentResult, AgentContext](
        run_limit=settings.agent.max_tool_calls,
        exit_behavior="error",
    ),
    RepeatedToolCallGuardMiddleware(non_mutating_tool_names=_NON_MUTATING_TOOL_NAMES),
)


def create_task_recurrence_rule_agent(model: str | BaseChatModel) -> AgentGraph:
    """Create an agent focused on recurrence-rule management."""
    return create_agent(
        model=model,
        tools=_TOOLS,
        system_prompt=TASK_RECURRENCE_RULE_AGENT_PROMPT,
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        middleware=_MIDDLEWARES,
        name="task_recurrence_rule_agent",
    )
