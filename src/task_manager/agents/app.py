import os
from uuid import UUID
from typing import Any
from datetime import datetime
from logging import getLogger
from collections.abc import Sequence

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from openai import BadRequestError, APIConnectionError
from langfuse.langchain import CallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, ToolMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from config import settings
from services.tags import TagService
from services.tasks import TaskService
from agents.types import AgentGraph
from agents.graph import build_agent_graph
from agents.progress import (
    emit_progress,
    AgentProgressCallback,
    AgentProgressCallbackHandler,
)
from agents.schemas.common import AgentContext, AgentResult, AgentStatus


PSYCOPG_DB_URL = f"{settings.db.database}://{settings.db.user}:{settings.db.password}@{settings.db.host}:{settings.db.port}/{settings.db.name}"
CONN_MAX_SIZE = 20

logger = getLogger(__name__)


class AgentApplication:
    """Application entry point for the agent graph and its infrastructure."""

    def __init__(self) -> None:
        self.db_url = PSYCOPG_DB_URL
        self.max_size = CONN_MAX_SIZE
        self._pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None
        self._graph: AgentGraph | None = None
        self._checkpointer: AsyncPostgresSaver | None = None

    async def initialize(self) -> None:
        """Open persistence resources and compile the agent graph once."""
        if self._graph is not None:
            logger.debug("AgentApplication is already initialized")
            return
        if self._pool is not None:
            raise RuntimeError("AgentApplication initialization is already in progress")

        logger.info("Initializing AgentApplication")
        try:
            self._pool = await self._create_conn_pool()
            self._graph = await self._build_graph()
            logger.info("AgentApplication initialized")
        except Exception:
            logger.exception("AgentApplication initialization failed")
            await self.close()
            raise

    async def run(
        self,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        task_service: TaskService,
        tag_service: TagService,
        progress_callback: AgentProgressCallback | None = None,
    ) -> AgentResult:
        """Run one user message in a chat-bound agent session."""
        logger.info("Running agent graph for user_id=%s chat_id=%s", user_id, chat_id)
        normalized_message = self._validate_message(message)
        if isinstance(normalized_message, AgentResult):
            logger.info(
                "Agent request rejected before graph invocation user_id=%s chat_id=%s status=%s",
                user_id,
                chat_id,
                normalized_message.status,
            )
            return normalized_message

        try:
            await emit_progress(
                progress_callback,
                "Analyzing the request...",
                stage="request_validation_completed",
                user_id=str(user_id),
                chat_id=str(chat_id),
            )
            graph_result = await self._invoke_graph(
                normalized_message,
                user_id=user_id,
                chat_id=chat_id,
                task_service=task_service,
                tag_service=tag_service,
                progress_callback=progress_callback,
            )
            result = self._to_agent_result(graph_result)
            logger.info(
                "Agent graph completed user_id=%s chat_id=%s status=%s",
                user_id,
                chat_id,
                result.status,
            )
            return result
        except GraphRecursionError:
            logger.exception(
                "Agent graph reached recursion limit user_id=%s chat_id=%s limit=%s",
                user_id,
                chat_id,
                settings.agent.max_iterations,
            )
            return AgentResult(
                status=AgentStatus.REJECTED,
                message=(
                    "I could not complete the request because the agent reached its execution "
                    "limit. Please narrow the request or try again."
                ),
            )
        except ToolCallLimitExceededError:
            logger.warning(
                "Agent tool call limit reached user_id=%s chat_id=%s limit=%s",
                user_id,
                chat_id,
                settings.agent.max_tool_calls,
            )
            return AgentResult(
                status=AgentStatus.REJECTED,
                message=(
                    "I could not complete the request within the tool-call limit. "
                    "Please narrow the request or try again."
                ),
            )
        except APIConnectionError:
            logger.exception(
                "Agent model connection failed user_id=%s chat_id=%s",
                user_id,
                chat_id,
            )
            return AgentResult(
                status=AgentStatus.REJECTED,
                message="The model endpoint is unavailable. Try again later.",
            )
        except BadRequestError as exc:
            if not _is_missing_tool_messages_error(exc):
                raise
            logger.exception(
                "Agent checkpoint contains incomplete tool-call messages user_id=%s chat_id=%s",
                user_id,
                chat_id,
            )
            repaired_messages = await self._repair_incomplete_tool_call_messages(chat_id)
            if repaired_messages:
                return await self._retry_after_checkpoint_repair(
                    normalized_message,
                    user_id=user_id,
                    chat_id=chat_id,
                    task_service=task_service,
                    tag_service=tag_service,
                    progress_callback=progress_callback,
                )

            return AgentResult(
                status=AgentStatus.REJECTED,
                message=(
                    "The agent conversation state contains an incomplete tool call. "
                    "No repairable checkpoint messages were found."
                ),
            )
        except Exception:
            logger.exception("Agent graph failed user_id=%s chat_id=%s", user_id, chat_id)
            raise

    async def reset_chat_checkpoint(self, chat_id: UUID) -> None:
        """Delete stored agent graph state for one chat session."""
        await self._get_checkpointer().adelete_thread(str(chat_id))
        logger.info("Agent checkpoint reset for chat_id=%s", chat_id)

    async def close(self) -> None:
        """Release graph persistence resources owned by this application."""
        pool = self._pool
        self._graph = None
        self._pool = None
        self._checkpointer = None

        if pool is not None:
            logger.info("Closing AgentApplication connection pool")
            await pool.close()
            logger.info("AgentApplication connection pool closed")

    async def _build_graph(self) -> AgentGraph:
        logger.debug("Building agent graph")
        checkpointer = await self._create_checkpointer()
        store = await self._create_store()
        self._checkpointer = checkpointer
        graph = build_agent_graph(checkpointer=checkpointer, store=store)
        logger.debug("Agent graph built")
        return graph

    async def _create_conn_pool(self) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
        if self._pool is not None:
            raise RuntimeError("AgentApplication connection pool is already created")

        logger.debug("Opening AgentApplication connection pool")
        pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
            conninfo=self.db_url,
            max_size=self.max_size,
            open=False,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
            },
        )
        await pool.open()
        logger.debug("AgentApplication connection pool opened")
        return pool

    async def _create_checkpointer(self) -> AsyncPostgresSaver:
        pool = self._get_pool()
        logger.debug("Initializing agent checkpointer")
        checkpointer = AsyncPostgresSaver(pool, serde=_create_checkpoint_serializer())
        # LangGraph owns this schema and may change it between package versions.
        await checkpointer.setup()
        logger.debug("Agent checkpointer initialized")
        return checkpointer

    async def _create_store(self) -> AsyncPostgresStore:
        pool = self._get_pool()
        logger.debug("Initializing agent store")
        store = AsyncPostgresStore(pool)
        # LangGraph owns this schema and may change it between package versions.
        await store.setup()
        logger.debug("Agent store initialized")
        return store

    def _validate_message(self, message: str) -> str | AgentResult:
        normalized_message = message.strip()
        if not normalized_message:
            return AgentResult(
                status=AgentStatus.NEEDS_CLARIFICATION,
                message="Please provide a task-management request.",
            )

        if len(normalized_message) > settings.agent.max_message_length:
            return AgentResult(
                status=AgentStatus.REJECTED,
                message="The request is too long to process safely.",
            )

        return normalized_message

    async def _invoke_graph(
        self,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        task_service: TaskService,
        tag_service: TagService,
        progress_callback: AgentProgressCallback | None = None,
    ) -> dict[str, Any]:
        return await self._get_graph().ainvoke(
            {"messages": [HumanMessage(content=_message_with_runtime_context(message))]},
            config=self._create_graph_config(
                chat_id,
                user_id=user_id,
                progress_callback=progress_callback,
            ),
            durability=settings.agent.checkpoint_durability,
            context=AgentContext(
                user_id=user_id,
                task_service=task_service,
                tag_service=tag_service,
            ),
        )

    async def _repair_incomplete_tool_call_messages(self, chat_id: UUID) -> int:
        config = self._create_graph_config(chat_id)
        state = await self._get_graph().aget_state(config)
        messages = _state_messages(state.values)
        message_updates = _build_incomplete_tool_call_repair_updates(messages)

        if not message_updates:
            logger.warning("No incomplete tool-call messages found for chat_id=%s", chat_id)
            return 0

        await self._get_graph().aupdate_state(
            config,
            {"messages": message_updates},
            as_node="model",
        )
        logger.info(
            "Removed incomplete tool-call checkpoint messages chat_id=%s count=%s",
            chat_id,
            len(message_updates),
        )
        return len(message_updates)

    async def _retry_after_checkpoint_repair(
        self,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        task_service: TaskService,
        tag_service: TagService,
        progress_callback: AgentProgressCallback | None = None,
    ) -> AgentResult:
        await emit_progress(
            progress_callback,
            "Continuing request processing...",
            stage="checkpoint_repaired",
            user_id=str(user_id),
            chat_id=str(chat_id),
        )
        try:
            graph_result = await self._invoke_graph(
                message,
                user_id=user_id,
                chat_id=chat_id,
                task_service=task_service,
                tag_service=tag_service,
                progress_callback=progress_callback,
            )
        except BadRequestError as exc:
            if not _is_missing_tool_messages_error(exc):
                raise
            logger.exception(
                "Agent checkpoint still contains incomplete tool-call messages after repair "
                "user_id=%s chat_id=%s",
                user_id,
                chat_id,
            )
            return AgentResult(
                status=AgentStatus.REJECTED,
                message=(
                    "The agent conversation state still contains an incomplete tool call "
                    "after repair."
                ),
            )

        return self._to_agent_result(graph_result)

    def _create_graph_config(
        self,
        chat_id: UUID,
        user_id: UUID | None = None,
        run_name: str = "task-manager-agent",
        progress_callback: AgentProgressCallback | None = None,
    ) -> RunnableConfig:
        return {
            "run_name": run_name,
            "recursion_limit": settings.agent.max_iterations,
            "configurable": {"thread_id": str(chat_id)},
            "callbacks": _create_agent_callbacks(progress_callback),
            "metadata": _create_langfuse_metadata(
                user_id=user_id,
                chat_id=chat_id,
            ),
        }

    def _to_agent_result(self, graph_result: dict[str, Any]) -> AgentResult:
        structured_response = graph_result.get("structured_response")
        if isinstance(structured_response, AgentResult):
            return structured_response

        logger.debug("Agent graph did not return structured response")
        return AgentResult(
            status=AgentStatus.COMPLETED,
            message=_last_message_content(graph_result) or "Done.",
        )

    def _get_graph(self) -> AgentGraph:
        if self._graph is None:
            raise RuntimeError("AgentApplication is not initialized")
        return self._graph

    def _get_pool(self) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
        if self._pool is None:
            raise RuntimeError("AgentApplication connection pool is not initialized")
        return self._pool

    def _get_checkpointer(self) -> AsyncPostgresSaver:
        if self._checkpointer is None:
            raise RuntimeError("AgentApplication checkpointer is not initialized")
        return self._checkpointer


def _last_message_content(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    if not messages:
        return ""

    last_message = messages[-1]
    if isinstance(last_message, AIMessage):
        content = last_message.content
    elif isinstance(last_message, dict):
        content = last_message.get("content", "")
    else:
        content = getattr(last_message, "content", "")

    if isinstance(content, str):
        return content

    return str(content)


def _message_with_runtime_context(message: str) -> str:
    return (
        "Runtime context:\n"
        f"- Current local datetime: {_current_datetime_context()}\n"
        "\n"
        "User request:\n"
        f"{message}"
    )


def _current_datetime_context() -> str:
    now = datetime.now().astimezone()
    utc_offset = now.strftime("%z")
    formatted_offset = f"{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else ""

    return (
        f"{now.date().isoformat()} {now.time().isoformat(timespec='seconds')} "
        f"{formatted_offset} {now.strftime('%A')}"
    )


def _state_messages(state_values: dict[str, Any] | Any) -> list[BaseMessage]:
    if not isinstance(state_values, dict):
        return []

    messages = state_values.get("messages")
    if not isinstance(messages, Sequence):
        return []

    return [message for message in messages if isinstance(message, BaseMessage)]


def _build_incomplete_tool_call_repair_updates(
    messages: Sequence[BaseMessage],
) -> list[RemoveMessage]:
    incomplete_message_index = _find_first_incomplete_tool_call_message_index(messages)
    if incomplete_message_index is None:
        return []

    messages_to_remove = messages[incomplete_message_index:]
    return [
        RemoveMessage(id=message.id) for message in messages_to_remove if message.id is not None
    ]


def _find_first_incomplete_tool_call_message_index(
    messages: Sequence[BaseMessage],
) -> int | None:
    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue

        expected_tool_call_ids = _message_tool_call_ids(message)
        next_index = index + 1
        while next_index < len(messages):
            next_message = messages[next_index]
            if not isinstance(next_message, ToolMessage):
                break

            expected_tool_call_ids.discard(next_message.tool_call_id)
            next_index += 1

        if expected_tool_call_ids:
            return index

    return None


def _message_tool_call_ids(message: AIMessage) -> set[str]:
    tool_call_ids: set[str] = set()
    for tool_call in message.tool_calls:
        tool_call_id = tool_call.get("id")
        if isinstance(tool_call_id, str):
            tool_call_ids.add(tool_call_id)

    return tool_call_ids


def _create_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            AgentResult,
            AgentStatus,
        ]
    )


def _is_missing_tool_messages_error(exc: BadRequestError) -> bool:
    message = str(exc)
    return "tool_calls" in message and "tool messages" in message and "tool_call_id" in message


def _create_langfuse_metadata(user_id: UUID | None, chat_id: UUID) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "langfuse_session_id": str(chat_id),
        "langfuse_tags": ["task-manager-agent"],
    }
    if user_id is not None:
        metadata["langfuse_user_id"] = str(user_id)

    return metadata


def _create_agent_callbacks(
    progress_callback: AgentProgressCallback | None = None,
) -> list[BaseCallbackHandler]:
    callbacks: list[BaseCallbackHandler] = []
    if progress_callback is not None:
        callbacks.append(AgentProgressCallbackHandler(progress_callback))
    if os.getenv("LANGFUSE_PUBLIC_KEY"):
        callbacks.append(CallbackHandler())
    return callbacks
