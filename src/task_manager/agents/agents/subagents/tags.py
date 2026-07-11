from typing import Any, cast
from collections.abc import Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.prompts import TAG_AGENT_PROMPT
from agents.types import AgentGraph
from agents.tools.tags import (
    get_tag,
    list_tags,
    create_tag,
    ensure_tag,
    update_tag,
    get_tag_history,
)
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.middlewares import RepeatedToolCallGuardMiddleware

_TOOLS = (
    list_tags,
    get_tag,
    get_tag_history,
    create_tag,
    ensure_tag,
    update_tag,
)
_NON_MUTATING_TOOL_NAMES = {
    list_tags.name,
    get_tag.name,
    get_tag_history.name,
    AgentResult.__name__,
}

_MIDDLEWARES: Sequence[AgentMiddleware[Any, AgentContext, Any]] = (
    ToolCallLimitMiddleware[AgentResult, AgentContext](
        run_limit=settings.agent.max_tool_calls,
        exit_behavior="error",
    ),
    RepeatedToolCallGuardMiddleware(non_mutating_tool_names=_NON_MUTATING_TOOL_NAMES),
)


def create_tag_agent(model: str | BaseChatModel) -> AgentGraph:
    """Create an agent focused on tag catalog workflows."""
    return create_agent(
        model=model,
        tools=_TOOLS,
        system_prompt=TAG_AGENT_PROMPT,
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        middleware=_MIDDLEWARES,
        name="tag_agent",
    )
