from uuid import uuid4
from typing import Any, cast
from datetime import datetime, timezone
from dataclasses import fields, dataclass

import pytest
import httpx
from pydantic import ValidationError
from openai import BadRequestError, APIConnectionError
from langgraph.runtime import Runtime
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.errors import GraphRecursionError
from langchain.agents.middleware.types import AgentState as LangChainAgentState
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

from config import settings
from agents.app import (
    AgentApplication,
)
from agents.progress import (
    AgentProgressEvent,
    AgentProgressCallbackHandler,
)
from agents.graph import ROUTE_TOOLS_NODE
from agents.routing import (
    ToolProfileRouter,
    parse_tool_profile_router_result,
    router_result_requests_context,
)
from agents.models import create_base_chat_model
from agents.schemas.common import (
    AgentContext,
    AgentResult,
    AgentStatus,
)
from agents.middlewares import (
    TaskManagerSummarizationMiddleware,
    CompletedRunMessageCleanupMiddleware,
    RepeatedToolCallGuardMiddleware,
)
from agents.schemas.tools import CreateTaskInput, ListTasksInput, UpdateTaskInput
from agents.tools.registry import ToolProfile, get_task_tools, get_read_tools
from agents.tools.system import get_current_datetime
from agents.tools.tasks import create_task
from dto.tasks import AddTask, ListTasksFilters
from domain.value_objects.tasks import Schedule, Task, TaskPriority, TaskStatus
from services.chats import ChatService
from services.tags import TagService
from services.tasks import TaskService


TaskAgentGraph = CompiledStateGraph[Any, AgentContext, Any, Any]
TEST_MODEL_NAME = "test-chat-model"
READ_TOOL_NAME = "read_tool"
ANOTHER_READ_TOOL_NAME = "another_read_tool"
MUTATION_TOOL_NAME = "mutation_tool"
FINAL_RESULT_TOOL_NAME = "final_result_tool"


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.payload = None
        self.config = None
        self.context = None
        self.durability = None

    async def ainvoke(self, input, *, config, context, durability):
        self.payload = input
        self.config = config
        self.context = context
        self.durability = durability
        return self.result


class RecursingFakeAgent:
    async def ainvoke(self, input, *, config, context, durability):
        raise GraphRecursionError("recursion limit reached")


class ToolLimitFakeAgent:
    async def ainvoke(self, input, *, config, context, durability):
        raise ToolCallLimitExceededError(
            thread_count=7,
            run_count=7,
            thread_limit=None,
            run_limit=6,
        )


class ConnectionErrorFakeAgent:
    async def ainvoke(self, input, *, config, context, durability):
        request = httpx.Request("POST", "https://example.test/chat/completions")
        raise APIConnectionError(request=request)


class FakeRouterModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests: list[Any] = []

    async def ainvoke(self, input, *, config):
        self.requests.append(input)
        return AIMessage(content=self.responses.pop(0))


class MissingToolMessagesFakeAgent:
    def __init__(self) -> None:
        self.invoke_count = 0
        self.messages = [
            HumanMessage(content="older request", id="human-old"),
            AIMessage(
                content="",
                id="ai-incomplete-tool-call",
                tool_calls=[
                    {
                        "name": MUTATION_TOOL_NAME,
                        "args": {"title": "Go to gym"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            HumanMessage(content="create a task", id="human-after-incomplete-tool-call"),
        ]
        self.updated_config = None
        self.updated_values = None
        self.updated_as_node = None

    async def ainvoke(self, input, *, config, context, durability):
        self.invoke_count += 1
        if self.invoke_count > 1:
            return {
                "structured_response": AgentResult(
                    status=AgentStatus.COMPLETED,
                    message="Created.",
                )
            }

        request = httpx.Request("POST", "https://example.test/chat/completions")
        response = httpx.Response(400, request=request)
        raise BadRequestError(
            "An assistant message with 'tool_calls' must be followed by tool messages "
            "responding to each 'tool_call_id'. "
            "(insufficient tool messages following tool_calls message)",
            response=response,
            body=None,
        )

    async def aget_state(self, config):
        return FakeStateSnapshot(values={"messages": self.messages})

    async def aupdate_state(self, config, values, as_node=None):
        self.updated_config = config
        self.updated_values = values
        self.updated_as_node = as_node
        return config


class PersistentMissingToolMessagesFakeAgent(MissingToolMessagesFakeAgent):
    async def ainvoke(self, input, *, config, context, durability):
        self.invoke_count += 1
        request = httpx.Request("POST", "https://example.test/chat/completions")
        response = httpx.Response(400, request=request)
        raise BadRequestError(
            "An assistant message with 'tool_calls' must be followed by tool messages "
            "responding to each 'tool_call_id'. "
            "(insufficient tool messages following tool_calls message)",
            response=response,
            body=None,
        )


class FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted_thread_id = None

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted_thread_id = thread_id


class FakeTaskService(TaskService):
    def __init__(self) -> None:
        self.created_for = None
        self.created_data = None

    async def create_task(self, user_id, data):
        self.created_for = user_id
        self.created_data = data
        return Task(
            task_id=uuid4(),
            title=data.title,
            status=TaskStatus.ACTIVE,
            priority=data.priority,
            due_at=data.due_at,
            created_at=datetime(2026, 6, 22, 10, 0),
            description=data.description,
        )


class FakeTagService(TagService):
    def __init__(self) -> None:
        pass


class FakeChatService(ChatService):
    def __init__(self) -> None:
        self.checked_user_id = None
        self.checked_chat_id = None

    async def check_user_can_use_chat(self, user_id, chat_id) -> None:
        self.checked_user_id = user_id
        self.checked_chat_id = chat_id


@dataclass(frozen=True)
class FakeRuntime:
    context: AgentContext


@dataclass(frozen=True)
class FakeStateSnapshot:
    values: dict[str, Any]


def test_task_agent_tool_profiles_are_not_the_full_catalog() -> None:
    full_tool_names = {tool.name for tool in get_task_tools(ToolProfile.FULL)}
    profile_tool_names = {
        profile: {tool.name for tool in get_task_tools(profile)}
        for profile in ToolProfile
        if profile != ToolProfile.FULL
    }

    assert full_tool_names
    assert all(tool_names for tool_names in profile_tool_names.values())
    assert all(tool_names < full_tool_names for tool_names in profile_tool_names.values())


def test_read_tool_registry_is_subset_of_profile_tools() -> None:
    for profile in ToolProfile:
        tool_names = {tool.name for tool in get_task_tools(profile)}
        read_tool_names = {tool.name for tool in get_read_tools(profile)}

        assert read_tool_names
        assert read_tool_names <= tool_names


@pytest.mark.parametrize("tool", get_task_tools())
def test_task_agent_tools_do_not_expose_runtime_context(tool) -> None:
    fields = set(tool.args_schema.model_json_schema()["properties"])

    assert "runtime" not in fields
    assert "user_id" not in fields
    assert "task_service" not in fields
    assert "tag_service" not in fields


@pytest.mark.asyncio
async def test_agent_application_passes_trusted_context_and_code_limits(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.setattr(
        "agents.app._current_datetime_context", lambda: "2026-07-02 12:30:00 +03:00 Thursday"
    )
    user_id = uuid4()
    chat_id = uuid4()
    task_service = FakeTaskService()
    tag_service = FakeTagService()
    chat_service = FakeChatService()
    expected = AgentResult(status=AgentStatus.COMPLETED, message="Created.")
    fake_agent = FakeAgent({"structured_response": expected})
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, fake_agent)

    result = await app.run(
        " create a task ",
        user_id=user_id,
        chat_id=chat_id,
        task_service=task_service,
        tag_service=tag_service,
    )

    assert result == expected
    assert fake_agent.payload is not None
    [message] = fake_agent.payload["messages"]
    assert isinstance(message, HumanMessage)
    assert "User request:\ncreate a task" in str(message.content)
    assert "Current local datetime: 2026-07-02 12:30:00 +03:00 Thursday" in str(
        message.content
    )
    assert fake_agent.config is not None
    assert fake_agent.config["recursion_limit"] == settings.agent.max_iterations
    assert fake_agent.config["configurable"]["thread_id"] == str(chat_id)
    assert fake_agent.config["callbacks"] == []
    assert fake_agent.config["metadata"]["langfuse_session_id"] == str(chat_id)
    assert fake_agent.config["metadata"]["langfuse_user_id"] == str(user_id)
    assert fake_agent.context == AgentContext(
        user_id=user_id,
        task_service=task_service,
        tag_service=tag_service,
    )
    assert fake_agent.durability == settings.agent.checkpoint_durability
    assert chat_service.checked_user_id is None
    assert chat_service.checked_chat_id is None


@pytest.mark.asyncio
async def test_agent_application_accepts_progress_callback(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    user_id = uuid4()
    chat_id = uuid4()
    events: list[AgentProgressEvent] = []
    fake_agent = FakeAgent(
        {"structured_response": AgentResult(status=AgentStatus.COMPLETED, message="Created.")}
    )
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, fake_agent)

    async def collect_progress(event: AgentProgressEvent) -> None:
        events.append(event)

    result = await app.run(
        "create a task",
        user_id=user_id,
        chat_id=chat_id,
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
        progress_callback=collect_progress,
    )

    assert result.message == "Created."
    assert events == [
        AgentProgressEvent(
            message="Analyzing the request...",
            metadata={
                "stage": "request_validation_completed",
                "user_id": str(user_id),
                "chat_id": str(chat_id),
            },
        )
    ]
    assert fake_agent.config is not None
    [callback] = fake_agent.config["callbacks"]
    assert isinstance(callback, AgentProgressCallbackHandler)


@pytest.mark.asyncio
async def test_agent_application_rejects_overlong_message_before_agent_call(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "max_message_length", 4)
    fake_agent = FakeAgent({})
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, fake_agent)

    result = await app.run(
        "too long",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.REJECTED
    assert fake_agent.payload is None


@pytest.mark.asyncio
async def test_agent_application_rejects_when_graph_recursion_limit_is_reached() -> None:
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, RecursingFakeAgent())

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.REJECTED
    assert "agent reached its execution limit" in result.message


@pytest.mark.asyncio
async def test_agent_application_rejects_when_tool_call_limit_is_reached() -> None:
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, ToolLimitFakeAgent())

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.REJECTED
    assert "tool-call limit" in result.message


@pytest.mark.asyncio
async def test_agent_application_rejects_when_model_connection_fails() -> None:
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, ConnectionErrorFakeAgent())

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.REJECTED
    assert "model endpoint is unavailable" in result.message


@pytest.mark.asyncio
async def test_agent_application_repairs_checkpoint_and_retries_when_tool_messages_are_missing() -> (
    None
):
    chat_id = uuid4()
    checkpointer = FakeCheckpointer()
    fake_agent = MissingToolMessagesFakeAgent()
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, fake_agent)
    app._checkpointer = cast(Any, checkpointer)

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=chat_id,
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.COMPLETED
    assert result.message == "Created."
    assert fake_agent.invoke_count == 2
    assert checkpointer.deleted_thread_id is None
    assert fake_agent.updated_as_node == "model"
    assert fake_agent.updated_config is not None
    assert fake_agent.updated_config["configurable"]["thread_id"] == str(chat_id)
    assert fake_agent.updated_values is not None
    removed_messages = fake_agent.updated_values["messages"]
    assert all(isinstance(message, RemoveMessage) for message in removed_messages)
    assert [message.id for message in removed_messages] == [
        "ai-incomplete-tool-call",
        "human-after-incomplete-tool-call",
    ]


@pytest.mark.asyncio
async def test_agent_application_rejects_when_checkpoint_repair_does_not_help() -> None:
    fake_agent = PersistentMissingToolMessagesFakeAgent()
    app = AgentApplication()
    app._graph = cast(TaskAgentGraph, fake_agent)

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.REJECTED
    assert "after repair" in result.message
    assert fake_agent.invoke_count == 2


@pytest.mark.asyncio
async def test_create_task_tool_uses_runtime_context_user_id() -> None:
    user_id = uuid4()
    tag_id = uuid4()
    task_service = FakeTaskService()
    runtime = FakeRuntime(
        context=AgentContext(
            user_id=user_id,
            task_service=task_service,
            tag_service=FakeTagService(),
        )
    )
    due_at = datetime(2026, 6, 23, 12, 0)
    schedule = Schedule(
        starts_at=datetime(2026, 6, 23, 10, 0),
        ends_at=datetime(2026, 6, 23, 11, 0),
    )

    result = await cast(Any, create_task).coroutine(
        runtime=runtime,
        title="Prepare report",
        due_at=due_at,
        description="Draft and send it",
        tag_ids=(tag_id,),
        priority=TaskPriority.HIGH,
        schedule=schedule,
    )

    assert result["status"] == "ok"
    assert result["task"]["title"] == "Prepare report"
    assert task_service.created_for == user_id
    assert task_service.created_data is not None
    assert task_service.created_data.due_at == due_at
    assert task_service.created_data.tag_ids == (tag_id,)
    assert task_service.created_data.schedule == schedule


@pytest.mark.asyncio
async def test_current_datetime_tool_returns_clock_context() -> None:
    result = await cast(Any, get_current_datetime).coroutine()

    assert isinstance(result, str)
    assert len(result.split()) == 4


@pytest.mark.asyncio
async def test_agent_application_returns_last_ai_message_when_structured_result_is_missing() -> None:
    app = AgentApplication()
    app._graph = cast(
        TaskAgentGraph,
        FakeAgent({"messages": [AIMessage(content="Done.")]})
    )

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result == AgentResult(status=AgentStatus.COMPLETED, message="Done.")


@pytest.mark.asyncio
async def test_agent_progress_callback_handler_uses_user_safe_messages() -> None:
    events: list[AgentProgressEvent] = []

    async def collect_progress(event: AgentProgressEvent) -> None:
        events.append(event)

    handler = AgentProgressCallbackHandler(collect_progress)
    await handler.on_chain_start(
        {"name": ROUTE_TOOLS_NODE},
        {},
        run_id=uuid4(),
        metadata={"langgraph_node": ROUTE_TOOLS_NODE},
    )
    await handler.on_chat_model_start(
        {"name": TEST_MODEL_NAME},
        [],
        run_id=uuid4(),
        metadata={"langgraph_node": ROUTE_TOOLS_NODE},
    )
    await handler.on_tool_start(
        {"name": READ_TOOL_NAME},
        "{}",
        run_id=uuid4(),
        metadata={"langgraph_node": ToolProfile.TASK_READ.value},
    )

    assert [event.message for event in events] == [
        "Selecting a processing path...",
        "Waiting for the model response...",
        "Checking data...",
    ]
    assert all(ROUTE_TOOLS_NODE not in event.message for event in events)
    assert all(READ_TOOL_NAME not in event.message for event in events)
    assert events[0].metadata["langgraph_node"] == ROUTE_TOOLS_NODE
    assert events[2].metadata["tool_name"] == READ_TOOL_NAME


@pytest.mark.asyncio
async def test_agent_progress_callback_handler_allows_missing_serialized_payload() -> None:
    events: list[AgentProgressEvent] = []

    async def collect_progress(event: AgentProgressEvent) -> None:
        events.append(event)

    handler = AgentProgressCallbackHandler(collect_progress)
    await handler.on_chain_start(
        cast(Any, None),
        {},
        run_id=uuid4(),
        metadata={"langgraph_node": ROUTE_TOOLS_NODE},
    )

    assert [event.message for event in events] == ["Selecting a processing path..."]
    assert events[0].metadata["serialized_name"] is None


@pytest.mark.asyncio
async def test_agent_progress_callback_handler_compacts_noisy_internal_cycles() -> None:
    events: list[AgentProgressEvent] = []

    async def collect_progress(event: AgentProgressEvent) -> None:
        events.append(event)

    handler = AgentProgressCallbackHandler(collect_progress)
    await handler.on_chain_start(
        {"name": ROUTE_TOOLS_NODE},
        {},
        run_id=uuid4(),
        metadata={"langgraph_node": ROUTE_TOOLS_NODE},
    )
    await handler.on_chat_model_start(
        {"name": TEST_MODEL_NAME},
        [],
        run_id=uuid4(),
        metadata={"langgraph_node": ROUTE_TOOLS_NODE},
    )
    await handler.on_chain_start(
        {"name": ROUTE_TOOLS_NODE},
        {},
        run_id=uuid4(),
        metadata={"langgraph_node": ROUTE_TOOLS_NODE},
    )
    await handler.on_chain_start(
        {"name": ToolProfile.SCHEDULE.value},
        {},
        run_id=uuid4(),
        metadata={"langgraph_node": ToolProfile.SCHEDULE.value},
    )

    for _ in range(4):
        await handler.on_tool_start(
            {"name": READ_TOOL_NAME},
            "{}",
            run_id=uuid4(),
            metadata={"langgraph_node": ToolProfile.SCHEDULE.value},
        )
        await handler.on_chat_model_start(
            {"name": TEST_MODEL_NAME},
            [],
            run_id=uuid4(),
            metadata={"langgraph_node": ToolProfile.SCHEDULE.value},
        )

    assert [event.message for event in events] == [
        "Selecting a processing path...",
        "Waiting for the model response...",
        "Processing the request...",
        "Checking data...",
        "Waiting for the model response...",
        "Checking data...",
        "Still working with your task data...",
    ]
    assert events[-1].metadata["stage"] == "ongoing_work"


def test_tool_profile_router_result_parser_accepts_plain_ai_message() -> None:
    assert (
        parse_tool_profile_router_result(AIMessage(content=ToolProfile.TASK_READ.value))
        == ToolProfile.TASK_READ
    )
    assert (
        parse_tool_profile_router_result(AIMessage(content=f'"{ToolProfile.SCHEDULE.value}"'))
        == ToolProfile.SCHEDULE
    )
    assert parse_tool_profile_router_result(AIMessage(content="unknown")) is None
    assert router_result_requests_context(AIMessage(content="needs_context")) is True


def test_task_manager_summarization_preserves_current_user_turn(monkeypatch) -> None:
    old_user_message = HumanMessage(content="old request", id="old-user")
    old_ai_message = AIMessage(content="old response", id="old-ai")
    current_user_message = HumanMessage(content="change the current task time", id="current-user")
    current_ai_message = AIMessage(
        content="",
        id="current-ai",
        tool_calls=[
            {
                "name": READ_TOOL_NAME,
                "args": {"search_text": "current task"},
                "id": "call-1",
            }
        ],
    )
    current_tool_message = ToolMessage(
        content='{"status": "ok"}',
        tool_call_id="call-1",
        id="current-tool",
    )
    middleware = TaskManagerSummarizationMiddleware(
        model=create_base_chat_model(),
        trigger=("messages", 3),
        keep=("messages", 1),
        summary_prompt="Messages to summarize:\n{messages}",
    )
    monkeypatch.setattr(middleware, "_create_summary", lambda messages: "new summary")

    update = middleware.before_model(
        cast(
            LangChainAgentState[AgentResult],
            {
                "messages": [
                    old_user_message,
                    old_ai_message,
                    current_user_message,
                    current_ai_message,
                    current_tool_message,
                ]
            },
        ),
        runtime=cast(Runtime[AgentContext], None),
    )

    assert update is not None
    messages = update["messages"]
    assert isinstance(messages[0], RemoveMessage)
    assert [message for message in messages if isinstance(message, HumanMessage)] == [
        messages[1],
        current_user_message,
    ]
    assert messages[-3:] == [
        current_user_message,
        current_ai_message,
        current_tool_message,
    ]
    assert "new summary" in str(messages[1].content)
    assert not any(
        (
            message in messages
            for message in [
                old_user_message,
                old_ai_message,
            ]
        )
    )


@pytest.mark.asyncio
async def test_tool_router_requests_context_when_current_message_is_ambiguous() -> None:
    model = FakeRouterModel(["needs_context"])
    router = ToolProfileRouter(cast(Any, model))

    decision = await router.select_profile(
        (
            "Runtime context:\n"
            "- Current local datetime: 2026-07-03 10:02:00 +03:00 Friday\n\n"
            "User request:\nMove it to the evening"
        ),
        config={},
    )

    assert decision.needs_context is True
    assert decision.profile is None
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_contextual_tool_router_uses_recent_context_when_requested() -> None:
    model = FakeRouterModel(["task_write"])
    router = ToolProfileRouter(cast(Any, model))
    messages = [
        HumanMessage(
            content=(
                "Runtime context:\n"
                "- Current local datetime: 2026-07-03 10:00:00 +03:00 Friday\n\n"
                "User request:\nAdd a task to go to the gym"
            )
        ),
        AIMessage(content="Created the task \"Go to the gym\"."),
        HumanMessage(
            content=(
                "Runtime context:\n"
                "- Current local datetime: 2026-07-03 10:01:00 +03:00 Friday\n\n"
                "User request:\nWhat about tomorrow?"
            )
        ),
        HumanMessage(
            content=(
                "Runtime context:\n"
                "- Current local datetime: 2026-07-03 10:02:00 +03:00 Friday\n\n"
                "User request:\nMove it to the evening"
            )
        ),
    ]

    profile = await router.select_profile_with_context(
        messages=messages,
        current_message=cast(str, messages[-1].content),
        config={},
    )

    assert profile == ToolProfile.TASK_WRITE
    assert len(model.requests) == 1
    context_message = model.requests[0][1][1]
    assert "Move it to the evening" in context_message
    assert "Add a task to go to the gym" in context_message
    assert 'Created the task "Go to the gym".' in context_message
    assert "What about tomorrow?" in context_message
    assert "Current local datetime" not in context_message


@pytest.mark.asyncio
async def test_contextual_tool_router_falls_back_to_full_when_context_is_still_insufficient() -> None:
    model = FakeRouterModel(["needs_context"])
    router = ToolProfileRouter(cast(Any, model))

    profile = await router.select_profile_with_context(
        messages=[HumanMessage(content="And this too")],
        current_message="And this too",
        config={},
    )

    assert profile == ToolProfile.FULL


def test_base_chat_model_uses_configured_timeout() -> None:
    model = create_base_chat_model()

    assert settings.agent.model_timeout_seconds == 30.0
    assert model.request_timeout == settings.agent.model_timeout_seconds


def test_completed_run_message_cleanup_removes_tool_traces() -> None:
    messages = [
        HumanMessage(content="create a task", id="human-1"),
        AIMessage(
            content="",
            id="ai-tool-1",
            tool_calls=[
                {
                    "name": MUTATION_TOOL_NAME,
                    "args": {"title": "Report"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"status":"ok"}',
            id="tool-1",
            name=MUTATION_TOOL_NAME,
            tool_call_id="call-1",
        ),
        AIMessage(
            content="",
            id="ai-result-1",
            tool_calls=[
                {
                    "name": FINAL_RESULT_TOOL_NAME,
                    "args": {"status": "completed", "message": "Created task Report."},
                    "id": "call-result-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="Returning structured response",
            id="tool-result-1",
            name=FINAL_RESULT_TOOL_NAME,
            tool_call_id="call-result-1",
        ),
    ]
    state = cast(
        LangChainAgentState[AgentResult],
        {
            "messages": messages,
            "structured_response": AgentResult(
                status=AgentStatus.COMPLETED,
                message="Created task Report.",
            ),
        },
    )

    update = CompletedRunMessageCleanupMiddleware().after_agent(
        state,
        runtime=cast(Runtime[AgentContext], None),
    )

    assert update is not None
    message_updates = update["messages"]
    assert [message.id for message in message_updates if isinstance(message, RemoveMessage)] == [
        "ai-tool-1",
        "tool-1",
        "ai-result-1",
        "tool-result-1",
    ]
    assert message_updates[-1] == AIMessage(content="Created task Report.")


def test_message_cleanup_keeps_tool_traces_when_clarification_is_needed() -> None:
    messages = [
        HumanMessage(content="complete report", id="human-1"),
        AIMessage(
            content="",
            id="ai-tool-1",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"search_text": "report"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"count":2}',
            id="tool-1",
            name=READ_TOOL_NAME,
            tool_call_id="call-1",
        ),
    ]
    state = cast(
        LangChainAgentState[AgentResult],
        {
            "messages": messages,
            "structured_response": AgentResult(
                status=AgentStatus.NEEDS_CLARIFICATION,
                message="Which report task should I complete?",
            ),
        },
    )

    update = CompletedRunMessageCleanupMiddleware().after_agent(
        state,
        runtime=cast(Runtime[AgentContext], None),
    )

    assert update is None


def test_repeated_tool_call_guard_guides_model_on_first_immediate_repeat() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"due_to": "2026-07-05", "statuses": ["active"]},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"status":"ok","count":4}',
            name=READ_TOOL_NAME,
            tool_call_id="call-1",
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"], "due_to": "2026-07-05"},
                    "id": "call-2",
                    "type": "tool_call",
                }
            ],
        ),
    ]
    state = cast(LangChainAgentState[AgentResult], {"messages": messages})

    update = RepeatedToolCallGuardMiddleware(
        non_mutating_tool_names={ANOTHER_READ_TOOL_NAME, READ_TOOL_NAME}
    ).after_model(
        state,
        runtime=cast(Runtime[AgentContext], None),
    )

    assert update is not None
    [message] = update["messages"]
    assert isinstance(message, ToolMessage)
    assert message.name == READ_TOOL_NAME
    assert message.tool_call_id == "call-2"
    assert message.status == "success"
    assert "skipped_repeated_tool_call" in str(message.content)
    assert "same result is already available" in str(message.content)
    assert "Continue using the previous tool result" in str(message.content)
    assert "structured_response" not in update


def test_repeated_tool_call_guard_forces_completion_after_guidance_is_ignored() -> None:
    first_repeat = AIMessage(
        content="",
        tool_calls=[
            {
                "name": READ_TOOL_NAME,
                "args": {"statuses": ["active"]},
                "id": "call-2",
                "type": "tool_call",
            }
        ],
    )
    guidance_update = RepeatedToolCallGuardMiddleware().after_model(
        cast(
            LangChainAgentState[AgentResult],
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": READ_TOOL_NAME,
                                "args": {"statuses": ["active"]},
                                "id": "call-1",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(content='{"status":"ok"}', name=READ_TOOL_NAME, tool_call_id="call-1"),
                    first_repeat,
                ]
            },
        ),
        runtime=cast(Runtime[AgentContext], None),
    )
    assert guidance_update is not None

    state = cast(
        LangChainAgentState[AgentResult],
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": READ_TOOL_NAME,
                            "args": {"statuses": ["active"]},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content='{"status":"ok"}', name=READ_TOOL_NAME, tool_call_id="call-1"),
                first_repeat,
                guidance_update["messages"][0],
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": READ_TOOL_NAME,
                            "args": {"statuses": ["active"]},
                            "id": "call-3",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        },
    )

    update = RepeatedToolCallGuardMiddleware(
        non_mutating_tool_names={ANOTHER_READ_TOOL_NAME, READ_TOOL_NAME}
    ).after_model(state, runtime=cast(Runtime[AgentContext], None))

    assert update is not None
    assert update["jump_to"] == "end"
    assert update["structured_response"] == AgentResult(
        status=AgentStatus.REJECTED,
        message=update["structured_response"].message,
    )
    [message] = update["messages"]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-3"


def test_repeated_tool_call_guard_does_not_cross_user_turn_boundary() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"]},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"status":"blocked_repeated_tool_call","guard":"task_manager_repeated_tool_call_guard"}',
            name=READ_TOOL_NAME,
            tool_call_id="call-1",
            status="error",
        ),
        HumanMessage(content="What tasks are there for tomorrow?"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"]},
                    "id": "call-2",
                    "type": "tool_call",
                }
            ],
        ),
    ]
    state = cast(LangChainAgentState[AgentResult], {"messages": messages})

    update = RepeatedToolCallGuardMiddleware(
        non_mutating_tool_names={ANOTHER_READ_TOOL_NAME, READ_TOOL_NAME}
    ).after_model(
        state,
        runtime=cast(Runtime[AgentContext], None),
    )

    assert update is None


def test_repeated_tool_call_guard_guides_same_non_mutating_tool_after_another_one() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"]},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content='{"status":"ok"}', name=READ_TOOL_NAME, tool_call_id="call-1"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": ANOTHER_READ_TOOL_NAME,
                    "args": {},
                    "id": "call-2",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="2026-07-02", name=ANOTHER_READ_TOOL_NAME, tool_call_id="call-2"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"]},
                    "id": "call-3",
                    "type": "tool_call",
                }
            ],
        ),
    ]
    state = cast(LangChainAgentState[AgentResult], {"messages": messages})

    update = RepeatedToolCallGuardMiddleware(
        non_mutating_tool_names={ANOTHER_READ_TOOL_NAME, READ_TOOL_NAME}
    ).after_model(state, runtime=cast(Runtime[AgentContext], None))

    assert update is not None
    [message] = update["messages"]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-3"


def test_repeated_tool_call_guard_allows_same_non_mutating_tool_after_mutation_tool() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"]},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content='{"status":"ok"}', name=READ_TOOL_NAME, tool_call_id="call-1"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": MUTATION_TOOL_NAME,
                    "args": {"task_id": "019f245c-98c5-75e6-9e25-22094b9549a5"},
                    "id": "call-2",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content='{"status":"ok"}', name=MUTATION_TOOL_NAME, tool_call_id="call-2"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": READ_TOOL_NAME,
                    "args": {"statuses": ["active"]},
                    "id": "call-3",
                    "type": "tool_call",
                }
            ],
        ),
    ]
    state = cast(LangChainAgentState[AgentResult], {"messages": messages})

    update = RepeatedToolCallGuardMiddleware().after_model(
        state,
        runtime=cast(Runtime[AgentContext], None),
    )

    assert update is None


def test_agent_schemas_document_fields() -> None:
    assert AgentResult.model_fields["status"].description
    assert AgentResult.model_fields["message"].description
    assert AgentContext.model_fields["user_id"].description
    assert ListTasksInput.model_fields["limit"].description
    assert CreateTaskInput.model_fields["due_at"].description
    for field_name in ("title", "description", "status", "priority", "due_at", "schedule"):
        assert "Omit or null leaves" in str(UpdateTaskInput.model_fields[field_name].description)

    assert "null is not a clear/delete operation" in str(
        UpdateTaskInput.model_fields["due_at"].description
    )
    assert "delete_task_schedule" in str(UpdateTaskInput.model_fields["schedule"].description)


def test_agent_tool_schemas_match_dto_arguments() -> None:
    assert _public_schema_fields(ListTasksInput) == _dataclass_fields(ListTasksFilters)
    assert _public_schema_fields(CreateTaskInput) == _dataclass_fields(AddTask)


def test_create_task_schema_rejects_timezone_aware_due_at() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CreateTaskInput.model_validate(
            {
                "title": "Go to gym",
                "due_at": datetime(2026, 7, 2, 23, 59, tzinfo=timezone.utc),
            }
        )

    assert "timezone" in str(exc_info.value)


def test_list_tasks_schema_rejects_timezone_aware_filters() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ListTasksInput.model_validate(
            {
                "due_from": datetime(2026, 7, 2, 0, 0, tzinfo=timezone.utc),
            }
        )

    assert "timezone" in str(exc_info.value)


def test_create_task_schema_rejects_timezone_aware_schedule() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CreateTaskInput.model_validate(
            {
                "title": "Go to gym",
                "due_at": datetime(2026, 7, 2, 23, 59),
                "schedule": {
                    "starts_at": datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc),
                    "ends_at": datetime(2026, 7, 2, 19, 0),
                },
            }
        )

    assert "schedule.starts_at must not include timezone offset" in str(exc_info.value)


def _public_schema_fields(schema_type) -> tuple[str, ...]:
    return tuple(field_name for field_name in schema_type.model_fields if field_name != "runtime")


def _dataclass_fields(dto_type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(dto_type))
