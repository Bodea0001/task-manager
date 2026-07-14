import asyncio
from json import loads
from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

import exceptions as app_exc
from agents.app import AgentApplication
from agents.progress import AgentPlanProgressCallback, AgentPlanProgressEvent, PlanStepProgress
from agents.run_locks import AgentRunLease, AgentRunLockManager
from agents.schemas.planning import PlanStatus, PlanStepStatus
from agents.schemas.result import AgentResult, AgentStatus
from dto.chats import AddChatMessage
from services.chats import ChatService
from services.tags import TagService
from services.tasks import TaskService
from domain.value_objects.users import User
from presentation.agent_stream import AgentStreamCoordinator
from presentation.app import create_app
from presentation.dependencies import get_agent_stream_coordinator, get_current_user


class ChatHistoryWorkflow:
    def __init__(self, user_id: UUID, chat_id: UUID) -> None:
        self.user_id = user_id
        self.chat_id = chat_id
        self.messages: list[tuple[str, str]] = []
        self.assistant_message_saved = asyncio.Event()

    async def check_user_can_use_chat(self, user_id: UUID, chat_id: UUID) -> None:
        if user_id != self.user_id or chat_id != self.chat_id:
            raise app_exc.ChatNotFound

    async def add_user_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: AddChatMessage,
    ) -> None:
        await self.check_user_can_use_chat(user_id, chat_id)
        self.messages.append(("user", data.content))

    async def add_assistant_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: AddChatMessage,
    ) -> None:
        await self.check_user_can_use_chat(user_id, chat_id)
        self.messages.append(("assistant", data.content))
        self.assistant_message_saved.set()


class AgentWorkflow:
    def __init__(
        self,
        *,
        result: AgentResult | None = None,
        delay_seconds: float = 0,
        error: Exception | None = None,
    ) -> None:
        self.result = result or AgentResult(
            status=AgentStatus.COMPLETED,
            message="You have one task today.",
            data={"task_count": 1},
        )
        self.delay_seconds = delay_seconds
        self.error = error

    async def run(
        self,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        task_service: TaskService,
        tag_service: TagService,
        plan_progress_callback: AgentPlanProgressCallback | None = None,
    ) -> AgentResult:
        if plan_progress_callback is not None:
            await plan_progress_callback(
                AgentPlanProgressEvent(
                    objective="Review today's tasks",
                    status=PlanStatus.EXECUTABLE,
                    steps=(
                        PlanStepProgress(
                            step_id="public-step",
                            title="Check today's tasks",
                            status=PlanStepStatus.COMPLETED,
                        ),
                    ),
                )
            )
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return self.result


class BlockingAgentWorkflow(AgentWorkflow):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(
        self,
        message: str,
        user_id: UUID,
        chat_id: UUID,
        task_service: TaskService,
        tag_service: TagService,
        plan_progress_callback: AgentPlanProgressCallback | None = None,
    ) -> AgentResult:
        self.started.set()
        await self.release.wait()
        return await super().run(
            message,
            user_id,
            chat_id,
            task_service,
            tag_service,
            plan_progress_callback,
        )


class InMemoryAgentRunLease:
    renew_interval_seconds = 60.0

    def __init__(self, manager: "InMemoryAgentRunLockManager", chat_id: UUID) -> None:
        self.manager = manager
        self.chat_id = chat_id

    async def renew(self) -> bool:
        return self.manager.active_leases.get(self.chat_id) is self

    async def release(self) -> None:
        if self.manager.active_leases.get(self.chat_id) is self:
            del self.manager.active_leases[self.chat_id]


class InMemoryAgentRunLockManager:
    def __init__(self) -> None:
        self.active_leases: dict[UUID, InMemoryAgentRunLease] = {}

    async def acquire(self, chat_id: UUID) -> AgentRunLease | None:
        if chat_id in self.active_leases:
            return None
        lease = InMemoryAgentRunLease(self, chat_id)
        self.active_leases[chat_id] = lease
        return lease


def _authenticated_user() -> User:
    return User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )


def _create_coordinator(
    agent: AgentWorkflow,
    chat_history: ChatHistoryWorkflow,
    *,
    heartbeat_seconds: float = 15,
    run_lock_manager: AgentRunLockManager | None = None,
) -> AgentStreamCoordinator:
    return AgentStreamCoordinator(
        agent=cast(AgentApplication, agent),
        task_service=cast(TaskService, object()),
        tag_service=cast(TagService, object()),
        chat_service=cast(ChatService, chat_history),
        run_lock_manager=run_lock_manager or InMemoryAgentRunLockManager(),
        heartbeat_seconds=heartbeat_seconds,
    )


def _create_agent_app(user: User, coordinator: AgentStreamCoordinator):
    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_agent_stream_coordinator] = lambda: coordinator
    return app


def _parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for record in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in record.splitlines())
        events.append((fields["event"], loads(fields["data"])))
    return events


@pytest.mark.asyncio
async def test_agent_endpoint_streams_public_progress_and_persists_conversation() -> None:
    user = _authenticated_user()
    chat_id = uuid4()
    history = ChatHistoryWorkflow(user.user_id, chat_id)
    coordinator = _create_coordinator(
        AgentWorkflow(delay_seconds=0.01),
        history,
        heartbeat_seconds=0.001,
    )
    app = _create_agent_app(user, coordinator)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/chats/{chat_id}/agent",
            json={"message": "What is due today?"},
        )

    events = _parse_sse(response.text)
    event_names = [name for name, _ in events]
    plan = next(payload for name, payload in events if name == "plan")
    result = events[-1]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert event_names[0] == "plan"
    assert "heartbeat" in event_names
    assert result == (
        "result",
        {
            "status": "completed",
            "message": "You have one task today.",
            "data": {"task_count": 1},
        },
    )
    assert plan == {
        "objective": "Review today's tasks",
        "status": "executable",
        "steps": [
            {
                "step_id": "public-step",
                "title": "Check today's tasks",
                "status": "completed",
            }
        ],
    }
    assert history.messages == [
        ("user", "What is due today?"),
        ("assistant", "You have one task today."),
    ]
    await coordinator.close()


@pytest.mark.asyncio
async def test_agent_endpoint_streams_safe_error_after_execution_failure() -> None:
    user = _authenticated_user()
    chat_id = uuid4()
    history = ChatHistoryWorkflow(user.user_id, chat_id)
    coordinator = _create_coordinator(
        AgentWorkflow(error=RuntimeError("sensitive internal detail")),
        history,
    )
    app = _create_agent_app(user, coordinator)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/chats/{chat_id}/agent",
            json={"message": "Show my tasks."},
        )

    events = _parse_sse(response.text)
    assert response.status_code == 200
    assert events[-1] == (
        "error",
        {
            "code": "agent_execution_failed",
            "message": "The agent request could not be completed.",
            "request_id": response.headers["X-Request-ID"],
        },
    )
    assert "sensitive internal detail" not in response.text
    assert history.messages == [("user", "Show my tasks.")]
    await coordinator.close()


@pytest.mark.asyncio
async def test_agent_endpoint_does_not_expose_or_modify_an_inaccessible_chat() -> None:
    user = _authenticated_user()
    owned_chat_id = uuid4()
    history = ChatHistoryWorkflow(user.user_id, owned_chat_id)
    coordinator = _create_coordinator(AgentWorkflow(), history)
    app = _create_agent_app(user, coordinator)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/chats/{uuid4()}/agent",
            json={"message": "Show my tasks."},
        )

    assert response.status_code == 404
    assert response.json()["code"] == "chat_not_found"
    assert history.messages == []
    await coordinator.close()


@pytest.mark.asyncio
async def test_agent_endpoint_rejects_a_second_run_for_the_same_chat() -> None:
    user = _authenticated_user()
    chat_id = uuid4()
    history = ChatHistoryWorkflow(user.user_id, chat_id)
    agent = BlockingAgentWorkflow()
    coordinator = _create_coordinator(agent, history)
    first_stream = await coordinator.start(
        message="First request",
        user_id=user.user_id,
        chat_id=chat_id,
        request_id="first-request",
    )
    await agent.started.wait()
    app = _create_agent_app(user, coordinator)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/chats/{chat_id}/agent",
            json={"message": "Second request"},
        )

    agent.release.set()
    first_events = [event async for event in first_stream.events()]

    assert response.status_code == 409
    assert response.json()["code"] == "agent_run_in_progress"
    assert first_events[-1].startswith("event: result\n")
    assert history.messages == [
        ("user", "First request"),
        ("assistant", "You have one task today."),
    ]
    await coordinator.close()


@pytest.mark.asyncio
async def test_disconnecting_stream_does_not_cancel_an_active_agent_run() -> None:
    user = _authenticated_user()
    chat_id = uuid4()
    history = ChatHistoryWorkflow(user.user_id, chat_id)
    agent = BlockingAgentWorkflow()
    coordinator = _create_coordinator(agent, history, heartbeat_seconds=0.001)
    stream = await coordinator.start(
        message="Keep processing",
        user_id=user.user_id,
        chat_id=chat_id,
        request_id="request-id",
    )
    events = stream.events()
    await agent.started.wait()

    first_event = await anext(events)
    await events.aclose()
    agent.release.set()
    await asyncio.wait_for(history.assistant_message_saved.wait(), timeout=1)

    assert first_event.startswith("event: heartbeat\n")
    assert history.messages == [
        ("user", "Keep processing"),
        ("assistant", "You have one task today."),
    ]
    await coordinator.close()
