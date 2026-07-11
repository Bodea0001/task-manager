from typing import Any, cast
from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.prompts import TASK_MUTATION_AGENT_PROMPT
from agents.types import AgentGraph
from agents.tools.tags import list_tags, ensure_tag
from agents.tools.system import get_current_datetime
from agents.tools.tasks import (
    get_task,
    list_tasks,
    update_task,
    cancel_task,
    reopen_task,
    complete_task,
    add_tag_to_task,
    remove_tag_from_task,
    delete_task_schedule,
)
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.middlewares import RepeatedToolCallGuardMiddleware

_TOOLS = (
    get_current_datetime,
    get_task,
    list_tasks,
    list_tags,
    ensure_tag,
    update_task,
    complete_task,
    reopen_task,
    cancel_task,
    add_tag_to_task,
    remove_tag_from_task,
    delete_task_schedule,
)
_NON_MUTATING_TOOL_NAMES = {
    get_current_datetime.name,
    get_task.name,
    list_tasks.name,
    list_tags.name,
    AgentResult.__name__,
}

_MIDDLEWARES: Sequence[AgentMiddleware[Any, AgentContext, Any]] = (
    ToolCallLimitMiddleware[AgentResult, AgentContext](
        run_limit=settings.agent.max_tool_calls,
        exit_behavior="error",
    ),
    RepeatedToolCallGuardMiddleware(non_mutating_tool_names=_NON_MUTATING_TOOL_NAMES),
)


def create_task_mutation_agent(model: str | BaseChatModel) -> AgentGraph:
    """Create an agent focused on changing existing task records."""
    return create_agent(
        model=model,
        tools=_TOOLS,
        system_prompt=TASK_MUTATION_AGENT_PROMPT,
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        middleware=_MIDDLEWARES,
        name="task_mutation_agent",
    )
