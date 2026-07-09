from typing import Any, Sequence, cast

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langgraph.store.base import BaseStore
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.prompts import TASK_MANAGER_SUMMARY_PROMPT, load_task_manager_prompt
from agents.types import AgentGraph
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.tools.registry import ToolProfile, get_task_tools, get_read_tools
from agents.middlewares import (
    TaskManagerSummarizationMiddleware,
    CompletedRunMessageCleanupMiddleware,
    RepeatedToolCallGuardMiddleware,
)


def create_task_manager_agent(
    model: str | BaseChatModel, store: BaseStore, tool_profile: ToolProfile
) -> AgentGraph:
    return create_agent(
        model=model,
        tools=get_task_tools(tool_profile),
        system_prompt=load_task_manager_prompt(),
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        store=store,
        middleware=_create_task_manager_middleware(model, tool_profile),
        name=f"task_manager_agent_{tool_profile.value}",
    )


def _create_task_manager_middleware(
    model: str | BaseChatModel,
    tool_profile: ToolProfile = ToolProfile.FULL,
) -> Sequence[AgentMiddleware[Any, AgentContext, Any]]:
    return (
        ToolCallLimitMiddleware[AgentResult, AgentContext](
            run_limit=settings.agent.max_tool_calls,
            exit_behavior="error",
        ),
        RepeatedToolCallGuardMiddleware(
            non_mutating_tool_names={tool.name for tool in get_read_tools(tool_profile)}
            | {AgentResult.__name__},
        ),
        TaskManagerSummarizationMiddleware(
            model=model,
            trigger=("messages", settings.agent.summarization_trigger_messages),
            keep=("messages", settings.agent.summarization_keep_messages),
            summary_prompt=TASK_MANAGER_SUMMARY_PROMPT,
        ),
        CompletedRunMessageCleanupMiddleware(),
    )
