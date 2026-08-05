import os
from uuid import UUID
from typing import Any, Literal
from collections.abc import Callable
from datetime import datetime
from logging import ERROR, INFO, WARNING, getLogger
from time import perf_counter

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from openai import APIConnectionError
from langfuse.langchain import CallbackHandler
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
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
from agents.agents import PlannerResultError
from agents.graph import build_agent_graph
from agents.progress import (
    AgentPlanProgressCallback,
    AgentPlanProgressCallbackHandler,
)
from agents.schemas.result import AgentResult, AgentStatus
from agents.schemas.context import AgentContext
from agents.schemas.planning import AgentPlan, PlanStatus, PlanStep, PlanStepStatus


PSYCOPG_DB_URL = f"{settings.db.database}://{settings.db.user}:{settings.db.password}@{settings.db.host}:{settings.db.port}/{settings.db.name}"
CONN_MAX_SIZE = 20

logger = getLogger(__name__)
type AgentRunOutcome = Literal["success", "rejected", "error"]
type ModelResponseCallback = Callable[[], None]


class _ModelResponseCallbackHandler(BaseCallbackHandler):
    def __init__(self, callback: ModelResponseCallback) -> None:
        self._callback = callback

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self._callback()


class AgentApplication:
    """Application entry point for the agent graph and its infrastructure."""

    def __init__(self) -> None:
        self.db_url = PSYCOPG_DB_URL
        self.max_size = CONN_MAX_SIZE
        self._pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None
        self._graph: AgentGraph | None = None
        self._checkpointer: AsyncPostgresSaver | None = None

    @property
    def is_initialized(self) -> bool:
        """Return whether all local resources required to run the graph exist."""
        return self._pool is not None and self._graph is not None and self._checkpointer is not None

    async def initialize(self) -> None:
        """Open persistence resources and compile the agent graph once."""
        if self._graph is not None:
            return
        if self._pool is not None:
            raise RuntimeError("AgentApplication initialization is already in progress")

        try:
            self._pool = await self._create_conn_pool()
            self._graph = await self._build_graph()
        except Exception:
            await self.close()
            raise

    async def run(
        self,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        task_service: TaskService,
        tag_service: TagService,
        plan_progress_callback: AgentPlanProgressCallback | None = None,
        model_response_callback: ModelResponseCallback | None = None,
        *,
        agent_run_id: UUID | None = None,
        message_id: UUID | None = None,
        preceding_unresolved_message_id: UUID | None = None,
        is_retry: bool = False,
    ) -> AgentResult:
        """Run one user message in a chat-bound agent session."""
        started_at = perf_counter()
        normalized_message = self._validate_message(message)
        if isinstance(normalized_message, AgentResult):
            _log_agent_run_ended(
                user_id,
                chat_id,
                normalized_message,
                started_at=started_at,
                outcome="rejected",
                reason=(
                    "empty_request"
                    if normalized_message.status is AgentStatus.NEEDS_CLARIFICATION
                    else "request_too_long"
                ),
            )
            return normalized_message

        reason: str | None = None
        limit: int | None = None
        error_type: str | None = None
        outcome: AgentRunOutcome = "success"
        log_level = INFO
        try:
            graph_result = await self._invoke_graph(
                normalized_message,
                user_id=user_id,
                chat_id=chat_id,
                task_service=task_service,
                tag_service=tag_service,
                plan_progress_callback=plan_progress_callback,
                model_response_callback=model_response_callback,
                agent_run_id=agent_run_id,
                message_id=message_id,
                preceding_unresolved_message_id=preceding_unresolved_message_id,
                is_retry=is_retry,
            )
            result, reason = self._to_agent_result(graph_result)
            if reason is not None:
                outcome = "rejected"
                log_level = WARNING
        except PlannerResultError:
            result = _planner_failure_result()
            reason = "invalid_planner_result"
            outcome = "rejected"
            log_level = WARNING
        except GraphRecursionError:
            result = AgentResult(
                status=AgentStatus.REJECTED,
                message=(
                    "I could not complete the request because the agent reached its execution "
                    "limit. Please narrow the request or try again."
                ),
            )
            reason = "recursion_limit_reached"
            limit = settings.agent.max_iterations
            outcome = "rejected"
            log_level = WARNING
        except ToolCallLimitExceededError:
            result = AgentResult(
                status=AgentStatus.REJECTED,
                message=(
                    "I could not complete the request within the tool-call limit. "
                    "Please narrow the request or try again."
                ),
            )
            reason = "tool_call_limit_reached"
            limit = settings.agent.max_tool_calls
            outcome = "rejected"
            log_level = WARNING
        except APIConnectionError as exc:
            result = AgentResult(
                status=AgentStatus.REJECTED,
                message="The model endpoint is unavailable. Try again later.",
            )
            reason = "model_connection_failed"
            error_type = type(exc).__name__
            outcome = "error"
            log_level = ERROR

        _log_agent_run_ended(
            user_id,
            chat_id,
            result,
            started_at=started_at,
            outcome=outcome,
            reason=reason,
            limit=limit,
            error_type=error_type,
            level=log_level,
        )
        return result

    async def reset_chat_checkpoint(self, chat_id: UUID) -> None:
        """Delete stored agent graph state for one chat session."""
        await self._get_checkpointer().adelete_thread(str(chat_id))
        logger.info(
            "event=agent_checkpoint_reset chat_id=%s outcome=success",
            chat_id,
            extra={
                "event": "agent_checkpoint_reset",
                "chat_id": str(chat_id),
                "outcome": "success",
            },
        )

    async def close(self) -> None:
        """Release graph persistence resources owned by this application."""
        pool = self._pool
        self._graph = None
        self._pool = None
        self._checkpointer = None

        if pool is not None:
            await pool.close()

    async def _build_graph(self) -> AgentGraph:
        checkpointer = await self._create_checkpointer()
        store = await self._create_store()
        self._checkpointer = checkpointer
        return build_agent_graph(checkpointer=checkpointer, store=store)

    async def _create_conn_pool(self) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
        if self._pool is not None:
            raise RuntimeError("AgentApplication connection pool is already created")

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
        return pool

    async def _create_checkpointer(self) -> AsyncPostgresSaver:
        pool = self._get_pool()
        checkpointer = AsyncPostgresSaver(pool, serde=_create_checkpoint_serializer())
        # LangGraph owns this schema and may change it between package versions.
        await checkpointer.setup()
        return checkpointer

    async def _create_store(self) -> AsyncPostgresStore:
        pool = self._get_pool()
        store = AsyncPostgresStore(pool)
        # LangGraph owns this schema and may change it between package versions.
        await store.setup()
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
        plan_progress_callback: AgentPlanProgressCallback | None = None,
        model_response_callback: ModelResponseCallback | None = None,
        agent_run_id: UUID | None = None,
        message_id: UUID | None = None,
        preceding_unresolved_message_id: UUID | None = None,
        is_retry: bool = False,
    ) -> dict[str, Any]:
        return await self._get_graph().ainvoke(
            {
                "messages": _agent_input_messages(
                    message,
                    agent_run_id=agent_run_id,
                    message_id=message_id,
                    preceding_unresolved_message_id=preceding_unresolved_message_id,
                    is_retry=is_retry,
                )
            },
            config=self._create_graph_config(
                chat_id,
                user_id=user_id,
                plan_progress_callback=plan_progress_callback,
                model_response_callback=model_response_callback,
            ),
            durability=settings.agent.checkpoint_durability,
            context=AgentContext(
                user_id=user_id,
                task_service=task_service,
                tag_service=tag_service,
            ),
        )

    def _create_graph_config(
        self,
        chat_id: UUID,
        user_id: UUID | None = None,
        run_name: str = "task-manager-agent",
        plan_progress_callback: AgentPlanProgressCallback | None = None,
        model_response_callback: ModelResponseCallback | None = None,
    ) -> RunnableConfig:
        return {
            "run_name": run_name,
            "recursion_limit": settings.agent.max_iterations,
            "configurable": {"thread_id": str(chat_id)},
            "callbacks": _create_agent_callbacks(
                plan_progress_callback,
                model_response_callback,
            ),
            "metadata": _create_langfuse_metadata(
                user_id=user_id,
                chat_id=chat_id,
            ),
        }

    def _to_agent_result(self, graph_result: dict[str, Any]) -> tuple[AgentResult, str | None]:
        structured_response = graph_result.get("structured_response")
        if isinstance(structured_response, AgentResult):
            return structured_response, None

        return (
            AgentResult(
                status=AgentStatus.REJECTED,
                message="The agent did not produce a valid structured response.",
            ),
            "invalid_structured_response",
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


def _planner_failure_result() -> AgentResult:
    return AgentResult(
        status=AgentStatus.REJECTED,
        message=(
            "The request could not be planned because the model returned an invalid response. "
            "Try again."
        ),
    )


def _log_agent_run_ended(
    user_id: UUID,
    chat_id: UUID,
    result: AgentResult,
    *,
    started_at: float,
    outcome: AgentRunOutcome = "success",
    reason: str | None = None,
    limit: int | None = None,
    error_type: str | None = None,
    level: int = INFO,
) -> None:
    duration_ms = _elapsed_ms(started_at)
    fields: dict[str, object] = {
        "event": "agent_run_ended",
        "user_id": str(user_id),
        "chat_id": str(chat_id),
        "outcome": outcome,
        "status": result.status.value,
        "duration_ms": duration_ms,
    }
    fields.update(
        {
            name: value
            for name, value in (
                ("reason", reason),
                ("limit", limit),
                ("error_type", error_type),
            )
            if value is not None
        }
    )
    logger.log(level, "event=agent_run_ended", extra=fields)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1_000, 3)


def _message_with_runtime_context(message: str) -> str:
    return (
        "Runtime context:\n"
        f"- Current local datetime: {_current_datetime_context()}\n"
        "\n"
        "User request:\n"
        f"{message}"
    )


def _agent_input_messages(
    message: str,
    agent_run_id: UUID | None,
    message_id: UUID | None,
    preceding_unresolved_message_id: UUID | None,
    is_retry: bool,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if preceding_unresolved_message_id is not None:
        messages.append(
            SystemMessage(
                id=f"unresolved-agent-request:{preceding_unresolved_message_id}",
                content=(
                    "The preceding user request did not reach a confirmed completion. "
                    "Do not assume it was fulfilled. Some operations may have completed, so "
                    "verify current state when it matters. Process only the current request "
                    "unless it explicitly returns to the preceding one."
                ),
                additional_kwargs={"lc_source": "agent_run_outcome"},
            )
        )

    messages.append(
        HumanMessage(
            id=str(message_id) if message_id is not None else None,
            content=_message_with_runtime_context(message),
        )
    )
    if is_retry:
        messages.append(
            SystemMessage(
                id=f"agent-request-retry:{agent_run_id or message_id}",
                content=(
                    "The user explicitly requested another attempt at the unresolved request "
                    "above. Re-evaluate it against current persisted state before performing "
                    "changes, and do not assume that earlier attempted operations failed."
                ),
                additional_kwargs={"lc_source": "agent_request_retry"},
            )
        )
    return messages


def _current_datetime_context() -> str:
    now = datetime.now().astimezone()
    utc_offset = now.strftime("%z")
    formatted_offset = f"{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else ""

    return (
        f"{now.date().isoformat()} {now.time().isoformat(timespec='seconds')} "
        f"{formatted_offset} {now.strftime('%A')}"
    )


def _create_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            AgentResult,
            AgentStatus,
            AgentPlan,
            PlanStatus,
            PlanStep,
            PlanStepStatus,
        ]
    )


def _create_langfuse_metadata(user_id: UUID | None, chat_id: UUID) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "langfuse_session_id": str(chat_id),
        "langfuse_tags": ["task-manager-agent"],
    }
    if user_id is not None:
        metadata["langfuse_user_id"] = str(user_id)

    return metadata


def _create_agent_callbacks(
    plan_progress_callback: AgentPlanProgressCallback | None = None,
    model_response_callback: ModelResponseCallback | None = None,
) -> list[BaseCallbackHandler]:
    callbacks: list[BaseCallbackHandler] = []
    if plan_progress_callback is not None:
        callbacks.append(AgentPlanProgressCallbackHandler(plan_progress_callback))
    if model_response_callback is not None:
        callbacks.append(_ModelResponseCallbackHandler(model_response_callback))
    if os.getenv("LANGFUSE_PUBLIC_KEY"):
        callbacks.append(CallbackHandler())
    return callbacks
