from dataclasses import dataclass
from typing import Any
from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel

from agents.prompts import TOOL_ROUTER_PROMPT
from agents.tools.registry import ToolProfile


TOOL_ROUTER_NEEDS_CONTEXT = "needs_context"


@dataclass(frozen=True)
class ToolRoutingDecision:
    """Router outcome for one request before optional context expansion."""

    profile: ToolProfile | None = None
    needs_context: bool = False


class ToolProfileRouter:
    """Classify user requests into the smallest sufficient tool profile."""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def select_profile(self, message: str, config: RunnableConfig) -> ToolRoutingDecision:
        """Classify the current request without adding conversation context."""
        result = await self._model.ainvoke(
            [
                ("system", TOOL_ROUTER_PROMPT),
                ("human", message),
            ],
            config=config,
        )
        profile = parse_tool_profile_router_result(result)
        if profile is not None:
            return ToolRoutingDecision(profile=profile)

        return ToolRoutingDecision(needs_context=router_result_requests_context(result))

    async def select_profile_with_context(
        self,
        messages: Sequence[BaseMessage],
        current_message: str,
        config: RunnableConfig,
    ) -> ToolProfile:
        """Classify an ambiguous request using a small recent conversation window."""
        result = await self._model.ainvoke(
            [
                ("system", TOOL_ROUTER_PROMPT),
                (
                    "human",
                    _router_context_message(messages, current_message=current_message),
                ),
            ],
            config=config,
        )
        profile = parse_tool_profile_router_result(result)
        if profile is None:
            return ToolProfile.FULL

        return profile


def parse_tool_profile_router_result(result: Any) -> ToolProfile | None:
    """Parse a model response into a supported tool profile."""
    content = result.content if isinstance(result, AIMessage) else result
    if not isinstance(content, str):
        return None

    normalized = content.strip().strip("`'\"").casefold()
    return _match_profile(normalized)


def router_result_requests_context(result: Any) -> bool:
    """Return whether the router explicitly asked for recent context."""
    content = result.content if isinstance(result, AIMessage) else result
    if not isinstance(content, str):
        return False

    return content.strip().strip("`'\"").casefold() == TOOL_ROUTER_NEEDS_CONTEXT


def _match_profile(message: str) -> ToolProfile | None:
    if message in ToolProfile:
        return next(profile for profile in ToolProfile if message == profile.value)
    return None


def _router_context_message(
    messages: Sequence[BaseMessage], current_message: str, human_limit: int = 2
) -> str:
    context = _recent_router_context(messages, human_limit=human_limit)
    if not context:
        context = "No recent conversation context is available."

    return (
        "Current request to classify:\n"
        f"{_strip_runtime_context(current_message)}\n\n"
        "Recent conversation context for disambiguation:\n"
        f"{context}\n\n"
        "Choose the smallest sufficient profile for the current request."
    )


def _recent_router_context(messages: Sequence[BaseMessage], human_limit: int = 2) -> str:
    last_human_index = _last_human_message_index(messages)
    if last_human_index is None:
        return ""

    prior_human_indices = [
        index
        for index, message in enumerate(messages[:last_human_index])
        if message.type == "human"
    ][-human_limit:]
    if not prior_human_indices:
        return ""

    lines: list[str] = []
    assistant_count = 0
    for position, human_index in enumerate(prior_human_indices, start=1):
        human_message = messages[human_index]
        lines.append(
            f"Previous user request {position}: {_strip_runtime_context(_message_text(human_message))}"
        )

        assistant_message = _assistant_response_after_human(
            messages,
            human_index=human_index,
            stop_index=last_human_index,
        )
        if assistant_message is not None and assistant_count < human_limit:
            assistant_count += 1
            lines.append(
                f"Assistant response {assistant_count}: {_message_text(assistant_message)}"
            )

    return "\n".join(lines)


def _last_human_message_index(messages: Sequence[BaseMessage]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].type == "human":
            return index

    return None


def _assistant_response_after_human(
    messages: Sequence[BaseMessage], *, human_index: int, stop_index: int
) -> AIMessage | None:
    for message in messages[human_index + 1 : stop_index]:
        if message.type == "human":
            return None

        if isinstance(message, AIMessage) and _message_text(message).strip():
            return message

    return None


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content

    return str(content)


def _strip_runtime_context(content: str) -> str:
    marker = "\nUser request:\n"
    if marker not in content:
        return content

    return content.rsplit(marker, 1)[-1]
