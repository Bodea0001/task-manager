from asyncio import (
    FIRST_COMPLETED,
    CancelledError,
    Queue,
    Task,
    create_task,
    gather,
    sleep,
    timeout,
    wait,
)
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from logging import getLogger
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

import exceptions as app_exc
from agents.app import AgentApplication
from agents.progress import AgentPlanProgressCallback, AgentPlanProgressEvent
from agents.run_locks import AgentRunLease, AgentRunLockManager
from agents.schemas.result import AgentResult
from dto.chats import AddChatMessage
from services.chats import ChatService
from services.tags import TagService
from services.tasks import TaskService
from presentation.schemas.agent import (
    AgentErrorResponse,
    AgentHeartbeatResponse,
    AgentPlanResponse,
    AgentResultResponse,
)


AGENT_STREAM_MEDIA_TYPE = "text/event-stream"
AGENT_STREAM_HEARTBEAT_SECONDS = 15.0
AGENT_STREAM_QUEUE_CAPACITY = 16

type AgentStreamEventName = Literal["plan", "result", "error", "heartbeat"]

logger = getLogger(__name__)


class _AgentRunLeaseLost(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _AgentStreamEvent:
    name: AgentStreamEventName
    payload: BaseModel
    terminal: bool = False

    def encode(self) -> str:
        return f"event: {self.name}\ndata: {self.payload.model_dump_json()}\n\n"


class _AgentEventChannel:
    """Keep public progress bounded while retaining the newest snapshots."""

    def __init__(self, capacity: int) -> None:
        self._queue: Queue[_AgentStreamEvent] = Queue(maxsize=capacity)
        self._attached = True

    def publish(self, event: _AgentStreamEvent) -> None:
        if not self._attached:
            return
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(event)

    async def receive(self) -> _AgentStreamEvent:
        return await self._queue.get()

    def detach(self) -> None:
        self._attached = False


class AgentEventStream:
    """Expose one agent run as an asynchronous sequence of SSE records."""

    def __init__(self, channel: _AgentEventChannel, heartbeat_seconds: float) -> None:
        self._channel = channel
        self._heartbeat_seconds = heartbeat_seconds

    async def events(self) -> AsyncGenerator[str]:
        """Yield public events and detach without cancelling side-effectful work."""
        try:
            while True:
                try:
                    async with timeout(self._heartbeat_seconds):
                        event = await self._channel.receive()
                except TimeoutError:
                    yield _AgentStreamEvent(
                        name="heartbeat",
                        payload=AgentHeartbeatResponse(),
                    ).encode()
                    continue

                yield event.encode()
                if event.terminal:
                    return
        finally:
            self._channel.detach()


class AgentStreamCoordinator:
    """Coordinate chat persistence, agent execution, and public progress events."""

    def __init__(
        self,
        *,
        agent: AgentApplication,
        task_service: TaskService,
        tag_service: TagService,
        chat_service: ChatService,
        run_lock_manager: AgentRunLockManager,
        heartbeat_seconds: float = AGENT_STREAM_HEARTBEAT_SECONDS,
        queue_capacity: int = AGENT_STREAM_QUEUE_CAPACITY,
    ) -> None:
        self._agent = agent
        self._task_service = task_service
        self._tag_service = tag_service
        self._chat_service = chat_service
        self._run_lock_manager = run_lock_manager
        self._heartbeat_seconds = heartbeat_seconds
        self._queue_capacity = queue_capacity
        self._tasks: set[Task[None]] = set()

    async def start(
        self,
        *,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        request_id: str,
    ) -> AgentEventStream:
        """Validate and persist a request before starting its event stream."""
        await self._chat_service.check_user_can_use_chat(user_id, chat_id)
        lease = await self._run_lock_manager.acquire(chat_id)
        if lease is None:
            raise app_exc.AgentRunInProgress

        try:
            await self._chat_service.add_user_message(
                user_id,
                chat_id,
                AddChatMessage(content=message),
            )
            channel = _AgentEventChannel(self._queue_capacity)
            task = create_task(
                self._run_agent(
                    message=message,
                    user_id=user_id,
                    chat_id=chat_id,
                    request_id=request_id,
                    channel=channel,
                    lease=lease,
                ),
                name=f"agent-run-{chat_id}",
            )
        except BaseException:
            await self._release_lease(lease, chat_id=chat_id, request_id=request_id)
            raise

        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return AgentEventStream(channel, self._heartbeat_seconds)

    async def close(self) -> None:
        """Cancel and await active runs during application shutdown."""
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await gather(*tasks, return_exceptions=True)

    async def _run_agent(
        self,
        *,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        request_id: str,
        channel: _AgentEventChannel,
        lease: AgentRunLease,
    ) -> None:
        async def publish_plan(event: AgentPlanProgressEvent) -> None:
            channel.publish(
                _AgentStreamEvent(
                    name="plan",
                    payload=AgentPlanResponse.from_progress(event),
                )
            )

        try:
            result = await self._invoke_agent_with_lease(
                lease,
                message=message,
                user_id=user_id,
                chat_id=chat_id,
                plan_progress_callback=publish_plan,
            )
            await self._chat_service.add_assistant_message(
                user_id,
                chat_id,
                AddChatMessage(content=result.message),
            )
            channel.publish(
                _AgentStreamEvent(
                    name="result",
                    payload=AgentResultResponse.from_result(result),
                    terminal=True,
                )
            )
            logger.info(
                "event=agent_stream_completed request_id=%s user_id=%s chat_id=%s "
                "outcome=success status=%s",
                request_id,
                user_id,
                chat_id,
                result.status,
                extra={
                    "event": "agent_stream_completed",
                    "request_id": request_id,
                    "user_id": str(user_id),
                    "chat_id": str(chat_id),
                    "outcome": "success",
                    "status": result.status,
                },
            )
        except CancelledError:
            logger.info(
                "event=agent_stream_completed request_id=%s user_id=%s chat_id=%s "
                "outcome=cancelled",
                request_id,
                user_id,
                chat_id,
                extra={
                    "event": "agent_stream_completed",
                    "request_id": request_id,
                    "user_id": str(user_id),
                    "chat_id": str(chat_id),
                    "outcome": "cancelled",
                },
            )
            raise
        except Exception as exc:
            error_code, error_message = _agent_stream_error(exc)
            logger.error(
                "event=agent_stream_completed request_id=%s user_id=%s chat_id=%s "
                "outcome=error error_type=%s",
                request_id,
                user_id,
                chat_id,
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
                extra={
                    "event": "agent_stream_completed",
                    "request_id": request_id,
                    "user_id": str(user_id),
                    "chat_id": str(chat_id),
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                },
            )
            channel.publish(
                _AgentStreamEvent(
                    name="error",
                    payload=AgentErrorResponse(
                        code=error_code,
                        message=error_message,
                        request_id=request_id,
                    ),
                    terminal=True,
                )
            )
        finally:
            await self._release_lease(lease, chat_id=chat_id, request_id=request_id)

    async def _invoke_agent_with_lease(
        self,
        lease: AgentRunLease,
        *,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        plan_progress_callback: AgentPlanProgressCallback,
    ) -> AgentResult:
        agent_task = create_task(
            self._agent.run(
                message,
                user_id,
                chat_id,
                self._task_service,
                self._tag_service,
                plan_progress_callback=plan_progress_callback,
            )
        )
        renewal_task = create_task(self._renew_lease(lease))
        try:
            done, _ = await wait(
                (agent_task, renewal_task),
                return_when=FIRST_COMPLETED,
            )
            if renewal_task in done:
                await renewal_task
                raise RuntimeError("Agent run lease renewal stopped unexpectedly")
            return await agent_task
        finally:
            for task in (agent_task, renewal_task):
                if not task.done():
                    task.cancel()
            await gather(agent_task, renewal_task, return_exceptions=True)

    @staticmethod
    async def _renew_lease(lease: AgentRunLease) -> None:
        while True:
            await sleep(lease.renew_interval_seconds)
            if not await lease.renew():
                raise _AgentRunLeaseLost

    @staticmethod
    async def _release_lease(
        lease: AgentRunLease,
        *,
        chat_id: UUID,
        request_id: str,
    ) -> None:
        try:
            await lease.release()
        except app_exc.AgentCoordinationUnavailable:
            logger.exception(
                "event=agent_run_lease_release_failed request_id=%s chat_id=%s",
                request_id,
                chat_id,
                extra={
                    "event": "agent_run_lease_release_failed",
                    "request_id": request_id,
                    "chat_id": str(chat_id),
                },
            )


def _agent_stream_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, app_exc.AgentCoordinationUnavailable):
        return (
            "agent_coordination_unavailable",
            "The agent request stopped because coordination became unavailable.",
        )
    if isinstance(exc, _AgentRunLeaseLost):
        return (
            "agent_run_lease_lost",
            "The agent request stopped because execution ownership was lost.",
        )
    return "agent_execution_failed", "The agent request could not be completed."
