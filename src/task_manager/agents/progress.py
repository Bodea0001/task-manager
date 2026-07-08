from uuid import UUID
from typing import Any
from logging import getLogger
from dataclasses import field, dataclass
from collections.abc import Awaitable, Callable, Mapping

from langchain_core.messages import BaseMessage
from langchain_core.callbacks import AsyncCallbackHandler

from agents.graph import ROUTE_TOOLS_NODE, ROUTE_TOOLS_WITH_CONTEXT_NODE
from agents.tools.registry import ToolProfile


logger = getLogger(__name__)


_SINGLE_EMIT_STAGES = frozenset({"routing", "agent_processing"})
_COMPACTED_WORK_STAGES = frozenset({"model_start", "tool_start"})
_MAX_VISIBLE_WORK_EVENTS = 4
_COMPACTED_WORK_MESSAGE = "Still working with your task data..."


@dataclass(frozen=True)
class AgentProgressEvent:
    """Transient agent execution progress event for UI updates."""

    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


AgentProgressCallback = Callable[[AgentProgressEvent], Awaitable[None]]


@dataclass(frozen=True)
class AgentProgressNodeMessage:
    message: str
    stage: str


def get_agent_progress_node_messages() -> dict[str, AgentProgressNodeMessage]:
    """Map graph nodes to generic user-facing progress messages."""
    return {
        ROUTE_TOOLS_NODE: AgentProgressNodeMessage(
            message="Selecting a processing path...",
            stage="routing",
        ),
        ROUTE_TOOLS_WITH_CONTEXT_NODE: AgentProgressNodeMessage(
            message="Selecting a processing path...",
            stage="routing",
        ),
        **{
            profile.value: AgentProgressNodeMessage(
                message="Processing the request...",
                stage="agent_processing",
            )
            for profile in ToolProfile
        },
    }


class AgentProgressCallbackHandler(AsyncCallbackHandler):
    """Converts internal LangChain callbacks into user-safe progress events."""

    def __init__(
        self,
        progress_callback: AgentProgressCallback,
        node_messages: Mapping[str, AgentProgressNodeMessage] | None = None,
    ) -> None:
        self._progress_callback = progress_callback
        self._node_messages = dict(node_messages or get_agent_progress_node_messages())
        self._last_message: str | None = None
        self._emitted_single_stages: set[str] = set()
        self._work_event_count = 0
        self._work_compacted_emitted = False

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        langgraph_node = (metadata or {}).get("langgraph_node")
        if not isinstance(langgraph_node, str):
            return

        progress_message = self._node_messages.get(langgraph_node)
        if progress_message is None:
            return

        await self._emit(
            progress_message.message,
            stage=progress_message.stage,
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            langgraph_node=langgraph_node,
            tags=tags,
            serialized_name=_serialized_name(serialized),
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        await self._emit_model_start(
            serialized=serialized,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
        )

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        await self._emit_model_start(
            serialized=serialized,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        await self._emit(
            "Checking data...",
            stage="tool_start",
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tool_name=_serialized_name(serialized),
            langgraph_node=(metadata or {}).get("langgraph_node"),
            tags=tags,
        )

    async def _emit_model_start(
        self,
        serialized: dict[str, Any],
        run_id: UUID,
        parent_run_id: UUID | None,
        tags: list[str] | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        await self._emit(
            "Waiting for the model response...",
            stage="model_start",
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            model_name=_serialized_name(serialized),
            langgraph_node=(metadata or {}).get("langgraph_node"),
            tags=tags,
        )

    async def _emit(self, message: str, **metadata: Any) -> None:
        compacted = self._compact_progress(message, metadata)
        if compacted is None:
            return

        message, metadata = compacted
        if message == self._last_message:
            return

        self._last_message = message
        await emit_progress(self._progress_callback, message, **metadata)

    def _compact_progress(
        self,
        message: str,
        metadata: dict[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        stage = metadata.get("stage")
        if not isinstance(stage, str):
            return message, metadata

        if stage in _SINGLE_EMIT_STAGES:
            if stage in self._emitted_single_stages:
                return None
            self._emitted_single_stages.add(stage)
            return message, metadata

        if stage not in _COMPACTED_WORK_STAGES:
            return message, metadata

        self._work_event_count += 1
        if self._work_event_count <= _MAX_VISIBLE_WORK_EVENTS:
            return message, metadata

        if self._work_compacted_emitted:
            return None

        self._work_compacted_emitted = True
        return (
            _COMPACTED_WORK_MESSAGE,
            {
                **metadata,
                "stage": "ongoing_work",
                "compacted_from_stage": stage,
                "compacted_work_event_count": self._work_event_count,
            },
        )


async def emit_progress(
    progress_callback: AgentProgressCallback | None,
    message: str,
    **metadata: Any,
) -> None:
    """Send a transient progress event without letting callback failures break runs."""
    if progress_callback is None:
        return

    try:
        await progress_callback(AgentProgressEvent(message=message, metadata=metadata))
    except Exception:
        logger.exception("Agent progress callback failed")


def _serialized_name(serialized: Any) -> str | None:
    if not isinstance(serialized, dict):
        return None

    name = serialized.get("name")
    if not isinstance(name, str):
        return None

    return name
