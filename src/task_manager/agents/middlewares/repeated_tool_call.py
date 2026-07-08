import json
from typing import Any
from logging import getLogger
from collections.abc import Iterable, Sequence

from langgraph.runtime import Runtime
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain.agents.middleware.types import AgentState as LangChainAgentState

from agents.schemas.common import AgentContext, AgentResult, AgentStatus


_GUARD_MARKER = "task_manager_repeated_tool_call_guard"
_SUMMARY_SOURCE = "summarization"
logger = getLogger(__name__)


class RepeatedToolCallGuardMiddleware(
    AgentMiddleware[LangChainAgentState[AgentResult], AgentContext, AgentResult]
):
    """Block immediate identical tool-call loops before they hit recursion limits."""

    def __init__(
        self,
        non_mutating_tool_names: Iterable[str] = (),
    ) -> None:
        super().__init__()
        self._non_mutating_tool_names = frozenset(non_mutating_tool_names)

    @hook_config(can_jump_to=["end"])
    def after_model(
        self, state: LangChainAgentState[AgentResult], runtime: Runtime[AgentContext]
    ) -> dict[str, Any] | None:
        messages = state.get("messages", ())
        current_call = _last_single_tool_call(messages)
        if current_call is None:
            return None

        if not _has_repeated_tool_call_without_new_result(
            messages,
            current_call,
            non_mutating_tool_names=self._non_mutating_tool_names,
        ):
            return None

        if _previous_call_was_guarded(messages):
            logger.warning(
                "Forcing agent completion after repeated non-mutating tool call tool=%s",
                current_call.get("name"),
            )
            return _build_forced_completion_update(current_call)

        logger.debug(
            "Guiding model away from repeated non-mutating tool call tool=%s",
            current_call.get("name"),
        )
        return {"messages": [_build_guidance_tool_message(current_call)]}


def _last_single_tool_call(messages: Sequence[BaseMessage]) -> dict[str, Any] | None:
    last_message = messages[-1] if messages else None
    if not isinstance(last_message, AIMessage):
        return None

    if len(last_message.tool_calls) != 1:
        return None

    return dict(last_message.tool_calls[0])


def _previous_single_tool_call(messages: Sequence[BaseMessage]) -> dict[str, Any] | None:
    if len(messages) < 2:
        return None

    for message in reversed(messages[:-1]):
        if _is_user_turn_boundary(message):
            return None

        if not isinstance(message, AIMessage):
            continue

        if len(message.tool_calls) != 1:
            return None

        return dict(message.tool_calls[0])

    return None


def _has_repeated_tool_call_without_new_result(
    messages: Sequence[BaseMessage],
    current_call: dict[str, Any],
    *,
    non_mutating_tool_names: frozenset[str],
) -> bool:
    previous_call = _previous_single_tool_call(messages)
    if previous_call is not None and _tool_call_signature(current_call) == _tool_call_signature(
        previous_call
    ):
        return True

    return _non_mutating_tool_repeated_without_mutation(
        messages,
        current_call,
        non_mutating_tool_names=non_mutating_tool_names,
    )


def _non_mutating_tool_repeated_without_mutation(
    messages: Sequence[BaseMessage],
    current_call: dict[str, Any],
    *,
    non_mutating_tool_names: frozenset[str],
) -> bool:
    if not _is_non_mutating_tool_call(current_call, non_mutating_tool_names):
        return False

    current_signature = _tool_call_signature(current_call)
    for message in reversed(messages[:-1]):
        if _is_user_turn_boundary(message):
            return False

        if not isinstance(message, AIMessage):
            continue

        tool_calls = [dict(tool_call) for tool_call in message.tool_calls]
        if any(
            _is_mutating_tool_call(
                tool_call,
                non_mutating_tool_names=non_mutating_tool_names,
            )
            for tool_call in tool_calls
        ):
            return False

        if len(tool_calls) == 1 and _tool_call_signature(tool_calls[0]) == current_signature:
            return True

    return False


def _previous_call_was_guarded(messages: Sequence[BaseMessage]) -> bool:
    if len(messages) < 2:
        return False

    for message in reversed(messages[:-1]):
        if _is_user_turn_boundary(message):
            return False

        if isinstance(message, AIMessage):
            return False

        if isinstance(message, ToolMessage) and _GUARD_MARKER in str(message.content):
            return True

    return False


def _is_user_turn_boundary(message: BaseMessage) -> bool:
    return message.type == "human" and message.additional_kwargs.get("lc_source") != _SUMMARY_SOURCE


def _is_non_mutating_tool_call(
    tool_call: dict[str, Any], non_mutating_tool_names: frozenset[str]
) -> bool:
    return tool_call.get("name") in non_mutating_tool_names


def _is_mutating_tool_call(
    tool_call: dict[str, Any],
    *,
    non_mutating_tool_names: frozenset[str],
) -> bool:
    name = tool_call.get("name")
    return isinstance(name, str) and name not in non_mutating_tool_names


def _tool_call_signature(tool_call: dict[str, Any]) -> str:
    payload = {
        "name": tool_call.get("name"),
        "args": tool_call.get("args", {}),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _build_guidance_tool_message(tool_call: dict[str, Any]) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "status": "skipped_repeated_tool_call",
                "guard": _GUARD_MARKER,
                "reason": (
                    "This tool call was skipped because the same result is already "
                    "available in the conversation."
                ),
                "instruction": (
                    "Continue using the previous tool result. Do not retry this tool call "
                    "with the same arguments unless a mutation tool changes the result."
                ),
            },
            ensure_ascii=False,
        ),
        name=tool_call.get("name"),
        tool_call_id=str(tool_call.get("id")),
    )


def _build_forced_completion_update(tool_call: dict[str, Any]) -> dict[str, Any]:
    message = (
        "Execution was stopped because the model repeatedly called the same tool "
        "with the same arguments and did not produce a final answer. Please retry "
        "or clarify the request."
    )
    return {
        "jump_to": "end",
        "messages": [
            ToolMessage(
                content=json.dumps(
                    {
                        "status": "blocked_repeated_tool_call",
                        "guard": _GUARD_MARKER,
                        "reason": (
                            "The model repeated the same tool call after being told to answer."
                        ),
                    },
                    ensure_ascii=False,
                ),
                name=tool_call.get("name"),
                tool_call_id=str(tool_call.get("id")),
                status="error",
            )
        ],
        "structured_response": AgentResult(status=AgentStatus.REJECTED, message=message),
    }
