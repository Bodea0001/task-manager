from typing import Sequence
from logging import getLogger

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Checkpointer
from langgraph.store.base import BaseStore
from langchain_core.language_models.chat_models import BaseChatModel

from agents.types import AgentGraph
from agents.routing import TOOL_ROUTER_NEEDS_CONTEXT, ToolProfileRouter
from agents.models import create_base_chat_model
from agents.schemas.common import AgentState, AgentContext
from agents.tools.registry import ToolProfile
from agents.agents.task_manager import create_task_manager_agent


ROUTE_TOOLS_NODE = "route_tools"
ROUTE_TOOLS_WITH_CONTEXT_NODE = "route_tools_with_context"
logger = getLogger(__name__)


def build_agent_graph(
    checkpointer: Checkpointer,
    store: BaseStore,
    model: str | BaseChatModel | None = None,
    router_model: BaseChatModel | None = None,
) -> AgentGraph:
    """Build the compiled LangGraph workflow used by AgentApplication."""
    graph_builder = AgentGraphBuilder(model=model, router_model=router_model)
    graph = graph_builder.build(checkpointer=checkpointer, store=store)
    return graph


class AgentGraphBuilder:
    """Build the agent workflow from routing nodes and profile-specific agents."""

    def __init__(
        self,
        model: str | BaseChatModel | None = None,
        router_model: BaseChatModel | None = None,
    ) -> None:
        self._model = model if model else create_base_chat_model()
        self._router_model = router_model if router_model else _default_router_model(self._model)

    def build(self, checkpointer: Checkpointer, store: BaseStore) -> AgentGraph:
        """Compile the graph with the provided persistence backends."""
        model = self._model
        router = ToolProfileRouter(self._router_model)
        graph = StateGraph(AgentState, context_schema=AgentContext)
        graph.add_node(ROUTE_TOOLS_NODE, self._create_route_tools_node(router))
        graph.add_node(
            ROUTE_TOOLS_WITH_CONTEXT_NODE,
            self._create_route_tools_with_context_node(router),
        )

        for profile in ToolProfile:
            graph.add_node(
                profile.value,
                create_task_manager_agent(
                    model=model,
                    store=store,
                    tool_profile=profile,
                ),
            )
            graph.add_edge(profile.value, END)

        graph.add_edge(START, ROUTE_TOOLS_NODE)
        graph.add_conditional_edges(
            ROUTE_TOOLS_NODE,
            self._router_destination,
            {
                ROUTE_TOOLS_WITH_CONTEXT_NODE: ROUTE_TOOLS_WITH_CONTEXT_NODE,
                **{profile.value: profile.value for profile in ToolProfile},
            },
        )
        graph.add_conditional_edges(
            ROUTE_TOOLS_WITH_CONTEXT_NODE,
            self._selected_profile_destination,
            {profile.value: profile.value for profile in ToolProfile},
        )

        return graph.compile(checkpointer=checkpointer, store=store, name="task_manager_agent")

    def _create_route_tools_node(self, router: ToolProfileRouter):
        async def route_tools(state: AgentState, config: RunnableConfig) -> dict[str, str]:
            decision = await router.select_profile(
                _last_human_message_content(state.get("messages", ())),
                config=config,
            )
            if decision.profile is not None:
                logger.debug("Agent tool router selected profile=%s", decision.profile.value)
                return {"selected_tool_profile": decision.profile.value}

            if decision.needs_context:
                logger.debug("Agent tool router requested recent context")
                return {"selected_tool_profile": TOOL_ROUTER_NEEDS_CONTEXT}

            logger.debug("Agent tool router fell back to profile=%s", ToolProfile.FULL.value)
            return {"selected_tool_profile": ToolProfile.FULL.value}

        return route_tools

    def _create_route_tools_with_context_node(self, router: ToolProfileRouter):
        async def route_tools_with_context(
            state: AgentState, config: RunnableConfig
        ) -> dict[str, str]:
            messages = state.get("messages", ())
            profile = await router.select_profile_with_context(
                messages=messages,
                current_message=_last_human_message_content(messages),
                config=config,
            )
            logger.debug(
                "Agent contextual tool router selected profile=%s",
                profile.value,
            )
            return {"selected_tool_profile": profile.value}

        return route_tools_with_context

    def _router_destination(self, state: AgentState) -> str:
        if state.get("selected_tool_profile") == TOOL_ROUTER_NEEDS_CONTEXT:
            return ROUTE_TOOLS_WITH_CONTEXT_NODE

        return self._selected_profile_destination(state)

    def _selected_profile_destination(self, state: AgentState) -> str:
        selected_tool_profile = state.get("selected_tool_profile")
        if selected_tool_profile is not None and selected_tool_profile in ToolProfile:
            return selected_tool_profile

        return ToolProfile.FULL.value


def _default_router_model(model: str | BaseChatModel) -> BaseChatModel:
    if isinstance(model, BaseChatModel):
        return model

    return create_base_chat_model()


def _last_human_message_content(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if message.type != "human":
            continue

        content = message.content
        if isinstance(content, str):
            return content

        return str(content)

    return ""
