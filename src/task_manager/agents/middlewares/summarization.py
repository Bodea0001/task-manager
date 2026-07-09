from typing import Any

from langgraph.runtime import Runtime
from langchain_core.messages import BaseMessage
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.types import AgentState as LangChainAgentState

from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext


SUMMARY_SOURCE = "summarization"


class TaskManagerSummarizationMiddleware(
    SummarizationMiddleware[AgentResult, AgentContext]
):
    """Summarize history while keeping only the newest summary and current turn."""

    def before_model(
        self, state: LangChainAgentState[Any], runtime: Runtime[AgentContext]
    ) -> dict[str, Any] | None:
        original_messages = list(state["messages"])
        update = super().before_model(state, runtime)
        return _keep_only_new_summary(update, original_messages)

    async def abefore_model(
        self, state: LangChainAgentState[Any], runtime: Runtime[AgentContext]
    ) -> dict[str, Any] | None:
        original_messages = list(state["messages"])
        update = await super().abefore_model(state, runtime)
        return _keep_only_new_summary(update, original_messages)


def _keep_only_new_summary(
    update: dict[str, Any] | None,
    original_messages: list[Any] | None = None,
) -> dict[str, Any] | None:
    if update is None:
        return None

    messages = update.get("messages")
    if not isinstance(messages, list):
        return update

    summary_seen = False
    filtered_messages: list[Any] = []
    for message in messages:
        if not _is_summary_message(message):
            filtered_messages.append(message)
            continue

        if summary_seen:
            continue

        summary_seen = True
        filtered_messages.append(message)

    current_turn = _latest_user_turn(original_messages or [])
    if current_turn and not _contains_message(filtered_messages, current_turn[0]):
        filtered_messages = [
            message
            for message in filtered_messages
            if not _contains_message(current_turn, message)
        ]
        filtered_messages.extend(current_turn)

    return {**update, "messages": filtered_messages}


def _is_summary_message(message: Any) -> bool:
    return (
        isinstance(message, BaseMessage)
        and message.additional_kwargs.get("lc_source") == SUMMARY_SOURCE
    )


def _latest_user_turn(messages: list[Any]) -> list[Any]:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if _is_user_message(message):
            return messages[index:]

    return []


def _is_user_message(message: Any) -> bool:
    return (
        isinstance(message, BaseMessage)
        and message.type == "human"
        and message.additional_kwargs.get("lc_source") != SUMMARY_SOURCE
    )


def _contains_message(messages: list[Any], candidate: Any) -> bool:
    candidate_id = getattr(candidate, "id", None)
    for message in messages:
        message_id = getattr(message, "id", None)
        if candidate_id is not None and message_id == candidate_id:
            return True
        if candidate_id is None and message is candidate:
            return True

    return False
