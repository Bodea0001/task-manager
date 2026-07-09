from typing import Any

from langgraph.graph.state import CompiledStateGraph

from agents.schemas.context import AgentContext


AgentGraph = CompiledStateGraph[Any, AgentContext, Any, Any]
