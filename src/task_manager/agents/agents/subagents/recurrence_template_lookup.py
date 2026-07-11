from typing import Any, cast
from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.prompts import RECURRENCE_TEMPLATE_LOOKUP_AGENT_PROMPT
from agents.types import AgentGraph
from agents.tools.tags import get_tag, list_tags
from agents.tools.system import get_current_datetime
from agents.tools.tasks import (
    get_task_recurrence_rules,
    get_task_recurrence_template,
    count_task_recurrence_templates,
    list_task_recurrence_templates,
    get_task_recurrence_template_history,
)
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.middlewares import RepeatedToolCallGuardMiddleware

_TOOLS = (
    get_current_datetime,
    list_task_recurrence_templates,
    count_task_recurrence_templates,
    get_task_recurrence_template,
    get_task_recurrence_rules,
    get_task_recurrence_template_history,
    list_tags,
    get_tag,
)

_MIDDLEWARES: Sequence[AgentMiddleware[Any, AgentContext, Any]] = (
    ToolCallLimitMiddleware[AgentResult, AgentContext](
        run_limit=settings.agent.max_tool_calls,
        exit_behavior="error",
    ),
    RepeatedToolCallGuardMiddleware(
        non_mutating_tool_names={tool.name for tool in _TOOLS} | {AgentResult.__name__},
    ),
)


def create_recurrence_template_lookup_agent(model: str | BaseChatModel) -> AgentGraph:
    """Create an agent focused on read-only recurring-template lookup."""
    return create_agent(
        model=model,
        tools=_TOOLS,
        system_prompt=RECURRENCE_TEMPLATE_LOOKUP_AGENT_PROMPT,
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        middleware=_MIDDLEWARES,
        name="recurrence_template_lookup_agent",
    )
