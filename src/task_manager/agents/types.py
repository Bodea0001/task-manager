from typing import Any

from langgraph.graph.state import CompiledStateGraph

from agents.schemas import AgentContext


AgentGraph = CompiledStateGraph[Any, AgentContext, Any, Any]
