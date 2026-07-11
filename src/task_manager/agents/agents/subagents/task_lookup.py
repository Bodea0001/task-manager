from typing import Any, cast
from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.prompts import TASK_LOOKUP_AGENT_PROMPT
from agents.types import AgentGraph
from agents.tools.tags import list_tags, get_tag
from agents.tools.tasks import (
    get_task,
    list_tasks,
    count_tasks,
    get_task_history,
    get_overdue_tasks,
)
from agents.tools.system import get_current_datetime
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.middlewares import RepeatedToolCallGuardMiddleware

_TOOLS = (
    get_current_datetime,
    get_task,
    list_tasks,
    count_tasks,
    get_overdue_tasks,
    get_task_history,
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


def create_task_lookup_agent(model: str | BaseChatModel) -> AgentGraph:
    """Create a read-only agent for searching and reviewing existing tasks."""
    return create_agent(
        model=model,
        tools=_TOOLS,
        system_prompt=TASK_LOOKUP_AGENT_PROMPT,
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        middleware=_MIDDLEWARES,
        name="task_lookup_agent",
    )
