from typing import Any, cast

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from agents.prompts import HELP_AGENT_PROMPT
from agents.types import AgentGraph
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext


def create_help_agent(model: str | BaseChatModel) -> AgentGraph:
    """Create an agent that explains product capabilities without using tools."""
    return create_agent(
        model=model,
        tools=[],
        system_prompt=HELP_AGENT_PROMPT,
        state_schema=cast(Any, AgentState),
        context_schema=AgentContext,
        response_format=ToolStrategy(AgentResult),
        checkpointer=None,
        name="help_agent",
    )
