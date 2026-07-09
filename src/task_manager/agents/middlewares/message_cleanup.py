from collections.abc import Sequence

from langgraph.runtime import Runtime
from langchain_core.messages import AIMessage, BaseMessage, RemoveMessage, ToolMessage
from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.middleware.types import AgentState as LangChainAgentState

from agents.schemas.result import AgentResult, AgentStatus
from agents.schemas.context import AgentContext


class CompletedRunMessageCleanupMiddleware(
    AgentMiddleware[LangChainAgentState[AgentResult], AgentContext, AgentResult]
):
    """Replace completed tool traces with one clean assistant message."""

    def after_agent(
        self, state: LangChainAgentState[AgentResult], runtime: Runtime[AgentContext]
    ) -> dict[str, list[BaseMessage]] | None:
        final_response = _get_completed_response(state)
        if final_response is None:
            return None

        message_updates = _build_cleanup_updates(
            messages=state["messages"], final_message=final_response.message
        )
        if not message_updates:
            return None

        return {"messages": message_updates}


def _get_completed_response(state: LangChainAgentState[AgentResult]) -> AgentResult | None:
    response = state.get("structured_response")
    if not isinstance(response, AgentResult):
        return None

    if response.status != AgentStatus.COMPLETED:
        return None

    return response


def _build_cleanup_updates(
    messages: Sequence[BaseMessage], final_message: str
) -> list[BaseMessage]:
    tool_call_ids = _collect_answered_tool_call_ids(messages)
    if not tool_call_ids:
        return []

    messages_to_remove = _select_tool_trace_messages(messages, tool_call_ids)
    remove_messages = _build_remove_messages(messages_to_remove)
    if not remove_messages:
        return []

    return [*remove_messages, AIMessage(content=final_message)]


def _collect_answered_tool_call_ids(messages: Sequence[BaseMessage]) -> set[str]:
    return {
        message.tool_call_id
        for message in messages
        if isinstance(message, ToolMessage) and message.tool_call_id
    }


def _select_tool_trace_messages(
    messages: Sequence[BaseMessage], tool_call_ids: set[str]
) -> list[BaseMessage]:
    return [message for message in messages if _is_tool_trace_message(message, tool_call_ids)]


def _is_tool_trace_message(message: BaseMessage, tool_call_ids: set[str]) -> bool:
    if isinstance(message, ToolMessage):
        return message.tool_call_id in tool_call_ids

    if not isinstance(message, AIMessage):
        return False

    return bool(_message_tool_call_ids(message) & tool_call_ids)


def _message_tool_call_ids(message: AIMessage) -> set[str]:
    tool_call_ids: set[str] = set()
    for tool_call in message.tool_calls:
        tool_call_id = tool_call.get("id")
        if isinstance(tool_call_id, str):
            tool_call_ids.add(tool_call_id)
    return tool_call_ids


def _build_remove_messages(messages: Sequence[BaseMessage]) -> list[RemoveMessage]:
    return [RemoveMessage(id=message.id) for message in messages if message.id is not None]
