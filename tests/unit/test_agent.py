from uuid import uuid4
from json import dumps
from typing import Any, cast
from datetime import datetime, timezone
from dataclasses import fields, dataclass

import pytest
import httpx
from pydantic import ValidationError
from openai import APIConnectionError
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.errors import GraphRecursionError
from langchain.agents.middleware.types import AgentState as LangChainAgentState
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

from config import settings
from agents.app import AgentApplication
from agents.graph import AgentGraphBuilder
from agents.agents import (
    PlannerAgent,
    PlannerResultError,
    ResponderAgent,
)
from agents.progress import (
    PLAN_PROGRESS_EVENT_NAME,
    AgentPlanProgressEvent,
    AgentPlanProgressCallbackHandler,
)
from agents.types import AgentGraph
from agents.schemas.result import AgentResult, AgentStatus
from agents.schemas.context import AgentContext
from agents.schemas.planning import (
    AgentPlan,
    CompiledSubAgent,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
)
from agents.middlewares import (
    RepeatedToolCallGuardMiddleware,
)
from agents.schemas.tools import (
    AddTaskRecurrenceRuleInput,
    AddTaskRecurrenceTemplateInput,
    AgentToolInput,
    CreateTaskInput,
    ListTaskRecurrenceTemplatesInput,
    ListTasksInput,
    UpdateTaskInput,
    UpdateTaskOccurrenceInput,
    UpdateTaskRecurrenceInput,
)
from agents.tools.system import get_current_datetime
from agents.tools.tasks import create_task
from dto.tasks import (
    AddTask,
    AddTaskRecurrence,
    AddTaskRecurrenceTemplate,
    ListTaskRecurrenceTemplatesFilters,
    ListTasksFilters,
    UpdateTaskData,
    UpdateTaskOccurrence,
    UpdateTaskRecurrence,
)
from domain.value_objects.tasks import Schedule, Task, TaskPriority, TaskStatus
from services.tags import TagService
from services.tasks import TaskService


READ_TOOL_NAME = "read_tool"
ANOTHER_READ_TOOL_NAME = "another_read_tool"
MUTATION_TOOL_NAME = "mutation_tool"
TEST_SUBAGENTS = (
    CompiledSubAgent(
        agent_id="task_lookup",
        display_name="TaskLookupAgent",
        description="Find tasks.",
        runnable=cast(AgentGraph, object()),
    ),
)


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.payload = None
        self.config = None
        self.context = None

    async def ainvoke(self, input, *, config, context, durability):
        self.payload = input
        self.config = config
        self.context = context
        return self.result


class ProgressEmittingFakeAgent(FakeAgent):
    async def ainvoke(self, input, *, config, context, durability):
        result = await super().ainvoke(
            input,
            config=config,
            context=context,
            durability=durability,
        )
        event = AgentPlanProgressEvent.model_validate(
            {
                "objective": "Create a task",
                "status": "executable",
                "steps": [
                    {
                        "step_id": "step_1",
                        "title": "Create the task",
                        "status": "completed",
                    }
                ],
            }
        )
        for callback in config.get("callbacks", ()):
            await callback.on_custom_event(
                PLAN_PROGRESS_EVENT_NAME,
                event.model_dump(mode="json"),
                run_id=uuid4(),
            )
        return result


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


class PlannerErrorFakeAgent:
    async def ainvoke(self, input, *, config, context, durability):
        raise PlannerResultError("Planner returned an invalid result after retry.")


class FakePlannerModel:
    def __init__(self, responses: str | list[str]) -> None:
        self.responses = [responses] if isinstance(responses, str) else list(responses)
        self.response_index = 0

    async def ainvoke(self, input, *, config):
        response_index = min(self.response_index, len(self.responses) - 1)
        self.response_index += 1
        return AIMessage(content=self.responses[response_index])


class FakeResponderModel:
    def __init__(self, response: str) -> None:
        self.response = response

    async def ainvoke(self, input, *, config):
        return AIMessage(content=self.response)


class SequentialResponderModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.response_index = 0

    async def ainvoke(self, input, *, config):
        response_index = min(self.response_index, len(self.responses) - 1)
        self.response_index += 1
        return AIMessage(content=self.responses[response_index])


class ConversationAwarePlannerModel:
    async def ainvoke(self, messages, *, config):
        has_previous_answer = any(
            isinstance(message, AIMessage) and message.content == "First response."
            for message in messages
        )
        is_follow_up = any(
            isinstance(message, HumanMessage) and "follow-up request" in str(message.content)
            for message in messages[-1:]
        )
        if is_follow_up and not has_previous_answer:
            return AIMessage(
                content=dumps(
                    {
                        "status": "needs_clarification",
                        "objective": "Continue the conversation",
                        "steps": [],
                        "clarification_question": "What should be continued?",
                    }
                )
            )

        objective = "Continue the conversation" if has_previous_answer else "Start conversation"
        return AIMessage(
            content=dumps(
                {
                    "status": "executable",
                    "objective": objective,
                    "steps": [
                        {
                            "title": objective,
                            "agent_id": "help",
                            "instruction": "Answer the delegated request.",
                        }
                    ],
                    "clarification_question": None,
                }
            )
        )


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="{}"))])


class ScenarioSubagentModel(FakeChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs: Any):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        message_text = "\n".join(str(message.content) for message in messages)
        if "Messages to summarize:" in message_text:
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="Historical conversation summary."))
                ]
            )

        leaked_parent_history = any(
            "parent-history-secret" in str(message.content) for message in messages
        )
        needs_clarification = "clarification-marker" in message_text
        rejected = leaked_parent_history or "rejection-marker" in message_text
        result = AgentResult(
            status=(
                AgentStatus.REJECTED
                if rejected
                else AgentStatus.NEEDS_CLARIFICATION
                if needs_clarification
                else AgentStatus.COMPLETED
            ),
            message=(
                "Delegated work rejected."
                if rejected
                else "More information is required."
                if needs_clarification
                else "Delegated work done."
            ),
        )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": AgentResult.__name__,
                                "args": result.model_dump(mode="json"),
                                "id": "agent-result",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class FailingSummarizationSubagentModel(ScenarioSubagentModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        if any("Messages to summarize:" in str(message.content) for message in messages):
            raise APIConnectionError(request=httpx.Request("POST", "https://example.test"))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


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


@dataclass(frozen=True)
class FakeRuntime:
    context: AgentContext


@pytest.mark.asyncio
async def test_planner_agent_returns_validated_plan() -> None:
    model = FakePlannerModel(
        dumps(
            {
                "status": "needs_clarification",
                "objective": "Update a task",
                "steps": [],
                "clarification_question": "Which task should be updated?",
            }
        )
    )
    planner = PlannerAgent(cast(Any, model), subagents=TEST_SUBAGENTS)
    config = {"metadata": {"test": "planner"}}

    result = await planner.create_plan(
        [HumanMessage(content="Update it")],
        config=cast(RunnableConfig, config),
    )

    assert result.status == PlanStatus.NEEDS_CLARIFICATION
    assert result.clarification_question == "Which task should be updated?"


@pytest.mark.asyncio
async def test_planner_agent_recovers_from_invalid_model_output() -> None:
    valid_result = dumps(
        {
            "status": "executable",
            "objective": "Find today's tasks",
            "steps": [
                {
                    "title": "Check today's tasks",
                    "agent_id": "task_lookup",
                    "instruction": "Find tasks relevant for today.",
                }
            ],
        }
    )
    model = FakePlannerModel(["not valid JSON", valid_result])
    planner = PlannerAgent(cast(Any, model), subagents=TEST_SUBAGENTS)

    result = await planner.create_plan(
        [HumanMessage(content="Which tasks are due today?")],
        config=cast(RunnableConfig, {}),
    )

    assert result.status == PlanStatus.EXECUTABLE


@pytest.mark.asyncio
async def test_planner_agent_rejects_persistently_invalid_model_output() -> None:
    model = FakePlannerModel(["not valid JSON", "still not valid JSON"])
    planner = PlannerAgent(cast(Any, model), subagents=TEST_SUBAGENTS)

    with pytest.raises(PlannerResultError, match="after retry"):
        await planner.create_plan(
            [HumanMessage(content="Which tasks are due today?")],
            config=cast(RunnableConfig, {}),
        )


@pytest.mark.asyncio
async def test_responder_agent_synthesizes_ordered_results() -> None:
    model = FakeResponderModel("One task was found. Which of the matching tasks should be updated?")
    responder = ResponderAgent(cast(Any, model))
    plan = AgentPlan(
        status=PlanStatus.EXECUTABLE,
        objective="Find and update a task",
        steps=[
            PlanStep(
                step_id="step_1",
                title="Find the task",
                agent_id="task_lookup",
                instruction="Find the requested task.",
                status=PlanStepStatus.COMPLETED,
            ),
            PlanStep(
                step_id="step_2",
                title="Update the task",
                agent_id="task_mutation",
                instruction="Update the selected task.",
                status=PlanStepStatus.COMPLETED,
            ),
        ],
    )
    step_results = {
        "step_1": AgentResult(
            status=AgentStatus.COMPLETED,
            message="Found one matching task.",
            data={"count": 1},
        ),
        "step_2": AgentResult(
            status=AgentStatus.NEEDS_CLARIFICATION,
            message="Several update targets remain possible.",
        ),
    }
    config = cast(RunnableConfig, {"metadata": {"test": "responder"}})

    result = await responder.respond(plan, step_results, config=config)

    assert result == AgentResult(
        status=AgentStatus.NEEDS_CLARIFICATION,
        message="One task was found. Which of the matching tasks should be updated?",
        data={"step_results": {"step_1": {"count": 1}}},
    )


@pytest.mark.asyncio
async def test_responder_agent_returns_planner_clarification() -> None:
    model = FakeResponderModel("This response should not be used.")
    responder = ResponderAgent(cast(Any, model))
    plan = AgentPlan(
        status=PlanStatus.NEEDS_CLARIFICATION,
        objective="Update a task",
        clarification_question="Which task should be updated?",
    )

    result = await responder.respond(plan, {}, config=cast(RunnableConfig, {}))

    assert result == AgentResult(
        status=AgentStatus.NEEDS_CLARIFICATION,
        message="Which task should be updated?",
    )


@pytest.mark.asyncio
async def test_planner_agent_rejects_unknown_subagent() -> None:
    model = FakePlannerModel(
        dumps(
            {
                "status": "executable",
                "objective": "Find today's tasks",
                "steps": [
                    {
                        "title": "Check today's tasks",
                        "agent_id": "unknown_agent",
                        "instruction": "Find tasks relevant for today.",
                    }
                ],
            }
        )
    )
    planner = PlannerAgent(
        cast(Any, model),
        subagents=TEST_SUBAGENTS,
    )

    with pytest.raises(PlannerResultError):
        await planner.create_plan(
            [HumanMessage(content="Which tasks are due today?")],
            config=cast(RunnableConfig, {}),
        )


@pytest.mark.asyncio
async def test_agent_graph_preserves_chat_history_without_exposing_it_to_subagents() -> None:
    checkpointer = InMemorySaver()
    graph = AgentGraphBuilder(
        planner_model=cast(Any, ConversationAwarePlannerModel()),
        subagent_model=ScenarioSubagentModel(),
        responder_model=cast(
            Any,
            SequentialResponderModel(["First response.", "Second response."]),
        ),
    ).build(checkpointer=checkpointer, store=InMemoryStore())
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid4())}}
    context = AgentContext(
        user_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    first_result = await graph.ainvoke(
        {"messages": [HumanMessage(content="parent-history-secret: initial request")]},
        config=config,
        context=context,
    )
    second_result = await graph.ainvoke(
        {"messages": [HumanMessage(content="follow-up request")]},
        config=config,
        context=context,
    )

    assert first_result["structured_response"] == AgentResult(
        status=AgentStatus.COMPLETED,
        message="First response.",
    )
    assert second_result["structured_response"] == AgentResult(
        status=AgentStatus.COMPLETED,
        message="Second response.",
    )


@pytest.mark.asyncio
async def test_agent_graph_executes_all_steps_and_reports_completed_progress() -> None:
    planner_model = FakePlannerModel(
        dumps(
            {
                "status": "executable",
                "objective": "Handle two independent requests",
                "steps": [
                    {
                        "title": "Explain deadlines",
                        "agent_id": "help",
                        "instruction": "Explain deadlines.",
                    },
                    {
                        "title": "Review tasks",
                        "agent_id": "task_lookup",
                        "instruction": "Review matching tasks.",
                    },
                ],
                "clarification_question": None,
            }
        )
    )
    events: list[AgentPlanProgressEvent] = []

    async def collect_progress(event: AgentPlanProgressEvent) -> None:
        events.append(event)

    graph = AgentGraphBuilder(
        planner_model=cast(Any, planner_model),
        subagent_model=ScenarioSubagentModel(),
        responder_model=cast(Any, FakeResponderModel("Both requests were handled.")),
    ).build(checkpointer=InMemorySaver(), store=InMemoryStore())
    config: RunnableConfig = {
        "configurable": {"thread_id": str(uuid4())},
        "callbacks": [AgentPlanProgressCallbackHandler(collect_progress)],
    }
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Handle both requests")]},
        config=config,
        context=AgentContext(
            user_id=uuid4(),
            task_service=FakeTaskService(),
            tag_service=FakeTagService(),
        ),
    )
    state = await graph.aget_state(config)

    assert result["structured_response"] == AgentResult(
        status=AgentStatus.COMPLETED,
        message="Both requests were handled.",
    )
    assert any(
        [step.status for step in event.steps] == [PlanStepStatus.COMPLETED, PlanStepStatus.PENDING]
        for event in events
    )
    assert [step.status for step in events[-1].steps] == [
        PlanStepStatus.COMPLETED,
        PlanStepStatus.COMPLETED,
    ]
    assert state.values.get("plan") is None
    assert state.values.get("step_results") == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("instruction", "expected_status"),
    [
        ("clarification-marker", AgentStatus.NEEDS_CLARIFICATION),
        ("rejection-marker", AgentStatus.REJECTED),
    ],
)
async def test_agent_graph_preserves_unsuccessful_step_outcomes(
    instruction: str,
    expected_status: AgentStatus,
) -> None:
    planner_model = FakePlannerModel(
        dumps(
            {
                "status": "executable",
                "objective": "Handle delegated work",
                "steps": [
                    {
                        "title": "Handle request",
                        "agent_id": "help",
                        "instruction": instruction,
                    }
                ],
                "clarification_question": None,
            }
        )
    )
    graph = AgentGraphBuilder(
        planner_model=cast(Any, planner_model),
        subagent_model=ScenarioSubagentModel(),
        responder_model=cast(Any, FakeResponderModel("The delegated outcome was preserved.")),
    ).build(checkpointer=InMemorySaver(), store=InMemoryStore())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Handle this request")]},
        config={"configurable": {"thread_id": str(uuid4())}},
        context=AgentContext(
            user_id=uuid4(),
            task_service=FakeTaskService(),
            tag_service=FakeTagService(),
        ),
    )

    assert result["structured_response"].status == expected_status


def test_agent_tool_schema_contract_does_not_expose_runtime_context() -> None:
    fields = set(AgentToolInput.model_json_schema()["properties"])

    assert "runtime" not in fields
    assert "user_id" not in fields
    assert "task_service" not in fields
    assert "tag_service" not in fields


@pytest.mark.asyncio
async def test_agent_application_passes_trusted_context_and_trace_identity(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.setattr(
        "agents.app._current_datetime_context", lambda: "2026-07-02 12:30:00 +03:00 Thursday"
    )
    user_id = uuid4()
    chat_id = uuid4()
    task_service = FakeTaskService()
    tag_service = FakeTagService()
    expected = AgentResult(status=AgentStatus.COMPLETED, message="Created.")
    fake_agent = FakeAgent({"structured_response": expected})
    app = AgentApplication()
    app._graph = cast(AgentGraph, fake_agent)

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
    assert "Current local datetime: 2026-07-02 12:30:00 +03:00 Thursday" in str(message.content)
    assert fake_agent.config is not None
    assert fake_agent.config["metadata"]["langfuse_session_id"] == str(chat_id)
    assert fake_agent.config["metadata"]["langfuse_user_id"] == str(user_id)
    assert fake_agent.context == AgentContext(
        user_id=user_id,
        task_service=task_service,
        tag_service=tag_service,
    )


@pytest.mark.asyncio
async def test_agent_application_accepts_plan_progress_callback(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    user_id = uuid4()
    chat_id = uuid4()
    events: list[AgentPlanProgressEvent] = []
    fake_agent = ProgressEmittingFakeAgent(
        {"structured_response": AgentResult(status=AgentStatus.COMPLETED, message="Created.")}
    )
    app = AgentApplication()
    app._graph = cast(AgentGraph, fake_agent)

    async def collect_progress(event: AgentPlanProgressEvent) -> None:
        events.append(event)

    result = await app.run(
        "create a task",
        user_id=user_id,
        chat_id=chat_id,
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
        plan_progress_callback=collect_progress,
    )

    assert result.message == "Created."
    assert len(events) == 1
    assert events[0].steps[0].status == PlanStepStatus.COMPLETED


@pytest.mark.asyncio
async def test_agent_application_returns_safe_result_for_invalid_planner_output() -> None:
    app = AgentApplication()
    app._graph = cast(AgentGraph, PlannerErrorFakeAgent())

    result = await app.run(
        "find today's tasks",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result.status == AgentStatus.REJECTED
    assert result.message == (
        "The request could not be planned because the model returned an invalid response. "
        "Try again."
    )


@pytest.mark.asyncio
async def test_agent_application_rejects_overlong_message_before_agent_call(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "max_message_length", 4)
    fake_agent = FakeAgent({})
    app = AgentApplication()
    app._graph = cast(AgentGraph, fake_agent)

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
    app._graph = cast(AgentGraph, RecursingFakeAgent())

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
    app._graph = cast(AgentGraph, ToolLimitFakeAgent())

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
    app._graph = cast(AgentGraph, ConnectionErrorFakeAgent())

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
async def test_agent_application_rejects_missing_structured_result() -> None:
    app = AgentApplication()
    app._graph = cast(AgentGraph, FakeAgent({"messages": [AIMessage(content="Done.")]}))

    result = await app.run(
        "create a task",
        user_id=uuid4(),
        chat_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )

    assert result == AgentResult(
        status=AgentStatus.REJECTED,
        message="The agent did not produce a valid structured response.",
    )


def test_agent_plan_progress_event_exposes_only_user_visible_plan_data() -> None:
    plan = AgentPlan(
        status=PlanStatus.EXECUTABLE,
        objective="Find today's tasks",
        steps=[
            PlanStep(
                step_id="step_1",
                title="Check today's tasks",
                agent_id="task_lookup",
                instruction="Use internal lookup details.",
                status=PlanStepStatus.IN_PROGRESS,
            )
        ],
    )

    event = AgentPlanProgressEvent.from_plan(plan)

    assert event.model_dump(mode="json") == {
        "objective": "Find today's tasks",
        "status": "executable",
        "steps": [
            {
                "step_id": "step_1",
                "title": "Check today's tasks",
                "status": "in_progress",
            }
        ],
    }


@pytest.mark.asyncio
async def test_agent_plan_progress_callback_handler_forwards_plan_snapshot() -> None:
    events: list[AgentPlanProgressEvent] = []

    async def collect_progress(event: AgentPlanProgressEvent) -> None:
        events.append(event)

    expected = AgentPlanProgressEvent.model_validate(
        {
            "objective": "Find today's tasks",
            "status": "executable",
            "steps": [
                {
                    "step_id": "step_1",
                    "title": "Check today's tasks",
                    "status": "completed",
                }
            ],
        }
    )
    handler = AgentPlanProgressCallbackHandler(collect_progress)

    await handler.on_custom_event(
        PLAN_PROGRESS_EVENT_NAME,
        expected.model_dump(mode="json"),
        run_id=uuid4(),
    )
    await handler.on_custom_event(
        "unrelated_event",
        {},
        run_id=uuid4(),
    )

    assert events == [expected]


@pytest.mark.asyncio
async def test_agent_graph_compacts_old_history_and_preserves_current_turn(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "summarization_trigger_messages", 3)
    monkeypatch.setattr(settings.agent, "summarization_keep_messages", 1)
    graph = _build_conversation_graph(ScenarioSubagentModel())
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid4())}}
    context = _agent_context()

    await graph.ainvoke(
        {"messages": [HumanMessage(content="first request")]},
        config=config,
        context=context,
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="current request")]},
        config=config,
        context=context,
    )
    state = await graph.aget_state(config)
    messages = state.values["messages"]

    assert result["structured_response"].status == AgentStatus.COMPLETED
    assert not any(message.content == "first request" for message in messages)
    assert any(message.content == "current request" for message in messages)


@pytest.mark.asyncio
async def test_agent_graph_preserves_history_when_summarization_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "summarization_trigger_messages", 3)
    monkeypatch.setattr(settings.agent, "summarization_keep_messages", 1)
    graph = _build_conversation_graph(FailingSummarizationSubagentModel())
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid4())}}
    context = _agent_context()

    await graph.ainvoke(
        {"messages": [HumanMessage(content="first request")]},
        config=config,
        context=context,
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="current request")]},
        config=config,
        context=context,
    )
    state = await graph.aget_state(config)
    messages = state.values["messages"]

    assert result["structured_response"].status == AgentStatus.COMPLETED
    assert any(message.content == "first request" for message in messages)
    assert any(message.content == "current request" for message in messages)


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
                    ToolMessage(
                        content='{"status":"ok"}', name=READ_TOOL_NAME, tool_call_id="call-1"
                    ),
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

    update = RepeatedToolCallGuardMiddleware(
        non_mutating_tool_names={ANOTHER_READ_TOOL_NAME, READ_TOOL_NAME}
    ).after_model(state, runtime=cast(Runtime[AgentContext], None))

    assert update is None


@pytest.mark.parametrize(
    ("schema_type", "dto_type", "operation_fields"),
    [
        (ListTasksInput, ListTasksFilters, ()),
        (CreateTaskInput, AddTask, ()),
        (UpdateTaskInput, UpdateTaskData, ("task_id",)),
        (
            ListTaskRecurrenceTemplatesInput,
            ListTaskRecurrenceTemplatesFilters,
            (),
        ),
        (AddTaskRecurrenceTemplateInput, AddTaskRecurrenceTemplate, ()),
        (AddTaskRecurrenceRuleInput, AddTaskRecurrence, ("template_id",)),
        (UpdateTaskRecurrenceInput, UpdateTaskRecurrence, ("recurrence_id",)),
        (
            UpdateTaskOccurrenceInput,
            UpdateTaskOccurrence,
            ("recurrence_id", "original_starts_at"),
        ),
    ],
)
def test_agent_tool_schemas_match_dto_arguments(
    schema_type,
    dto_type,
    operation_fields: tuple[str, ...],
) -> None:
    schema_fields = tuple(
        field_name
        for field_name in _public_schema_fields(schema_type)
        if field_name not in operation_fields
    )

    assert schema_fields == _dataclass_fields(dto_type)


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


def _build_conversation_graph(subagent_model: BaseChatModel) -> AgentGraph:
    planner_response = dumps(
        {
            "status": "executable",
            "objective": "Handle the current request",
            "steps": [
                {
                    "title": "Handle request",
                    "agent_id": "help",
                    "instruction": "Answer the delegated request.",
                }
            ],
            "clarification_question": None,
        }
    )
    return AgentGraphBuilder(
        planner_model=cast(Any, FakePlannerModel(planner_response)),
        subagent_model=subagent_model,
        responder_model=cast(Any, FakeResponderModel("Request handled.")),
    ).build(checkpointer=InMemorySaver(), store=InMemoryStore())


def _agent_context() -> AgentContext:
    return AgentContext(
        user_id=uuid4(),
        task_service=FakeTaskService(),
        tag_service=FakeTagService(),
    )
