from langgraph.graph import END, START, StateGraph
from langgraph.types import Checkpointer
from langgraph.store.base import BaseStore
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from agents.types import AgentGraph
from agents.models import (
    create_planner_chat_model,
    create_responder_chat_model,
    create_subagent_chat_model,
)
from agents.agents import (
    PlannerAgent,
    ResponderAgent,
    create_tag_agent,
    create_help_agent,
    create_schedule_agent,
    create_task_lookup_agent,
    create_task_creation_agent,
    create_task_mutation_agent,
    create_task_occurrence_agent,
    create_task_recurrence_rule_agent,
    create_recurrence_template_lookup_agent,
    create_recurrence_template_creation_agent,
    create_recurrence_template_mutation_agent,
)
from agents.nodes import (
    PlannerHistorySummarizationNode,
    PlannerNode,
    PlanExecutorNode,
    PlanResponderNode,
    PlanStepStartNode,
)
from agents.prompts import PLANNER_SUMMARY_PROMPT
from agents.schemas.state import AgentState
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext
from agents.schemas.planning import CompiledSubAgent
from agents.nodes.execution import plan_has_more_steps, plan_is_executable


SUMMARIZE_HISTORY_NODE = "summarize_history"
PLAN_NODE = "plan_request"
START_STEP_NODE = "start_step"
EXECUTE_STEP_NODE = "execute_step"
RESPOND_NODE = "respond"


def build_agent_graph(
    checkpointer: Checkpointer,
    store: BaseStore,
    subagent_model: str | BaseChatModel | None = None,
    planner_model: BaseChatModel | None = None,
    responder_model: BaseChatModel | None = None,
) -> AgentGraph:
    """Build the compiled LangGraph workflow used by AgentApplication."""
    graph_builder = AgentGraphBuilder(
        subagent_model=subagent_model,
        planner_model=planner_model,
        responder_model=responder_model,
    )
    graph = graph_builder.build(checkpointer=checkpointer, store=store)
    return graph


class AgentGraphBuilder:
    """Build the planner-driven multi-agent workflow."""

    def __init__(
        self,
        subagent_model: str | BaseChatModel | None = None,
        planner_model: BaseChatModel | None = None,
        responder_model: BaseChatModel | None = None,
    ) -> None:
        self._subagent_model = subagent_model if subagent_model else create_subagent_chat_model()
        self._planner_model = planner_model if planner_model else create_planner_chat_model()
        self._responder_model = (
            responder_model if responder_model else create_responder_chat_model()
        )

    def build(self, checkpointer: Checkpointer, store: BaseStore) -> AgentGraph:
        """Compile the graph with the provided persistence backends."""
        subagents = _create_subagents(self._subagent_model)
        subagents_by_id = {subagent.agent_id: subagent for subagent in subagents}
        planner = PlannerAgent(self._planner_model, subagents=subagents)
        responder = ResponderAgent(self._responder_model)
        summarization = SummarizationMiddleware[AgentResult, AgentContext](
            model=self._subagent_model,
            trigger=("messages", settings.agent.summarization_trigger_messages),
            keep=("messages", settings.agent.summarization_keep_messages),
            summary_prompt=PLANNER_SUMMARY_PROMPT,
        )

        graph = StateGraph(AgentState, context_schema=AgentContext)
        graph.add_node(
            SUMMARIZE_HISTORY_NODE,
            PlannerHistorySummarizationNode(summarization),
        )
        graph.add_node(PLAN_NODE, PlannerNode(planner))
        graph.add_node(START_STEP_NODE, PlanStepStartNode())
        graph.add_node(EXECUTE_STEP_NODE, PlanExecutorNode(subagents_by_id))
        graph.add_node(RESPOND_NODE, PlanResponderNode(responder))

        graph.add_edge(START, SUMMARIZE_HISTORY_NODE)
        graph.add_edge(SUMMARIZE_HISTORY_NODE, PLAN_NODE)
        graph.add_conditional_edges(
            PLAN_NODE,
            plan_is_executable,
            {
                "execute": START_STEP_NODE,
                "respond": RESPOND_NODE,
            },
        )
        graph.add_edge(START_STEP_NODE, EXECUTE_STEP_NODE)
        graph.add_conditional_edges(
            EXECUTE_STEP_NODE,
            plan_has_more_steps,
            {
                "start": START_STEP_NODE,
                "respond": RESPOND_NODE,
            },
        )
        graph.add_edge(RESPOND_NODE, END)

        return graph.compile(checkpointer=checkpointer, store=store, name="task_manager_agent")


def _create_subagents(model: str | BaseChatModel) -> tuple[CompiledSubAgent, ...]:
    return (
        CompiledSubAgent(
            agent_id="help",
            display_name="HelpAgent",
            description=(
                "Explain user-facing Task Manager capabilities, request phrasing, and "
                "clarification behavior. Use for product guidance only, never for current "
                "user data or task-management actions."
            ),
            runnable=create_help_agent(model),
        ),
        CompiledSubAgent(
            agent_id="task_lookup",
            display_name="TaskLookupAgent",
            description=(
                "Read existing tasks: find, list, count, inspect status, deadlines, schedules, "
                "tags, overdue work, and task history. Use for ordinary or already materialized "
                "tasks when no data should be changed, not for recurring-template lookup."
            ),
            runnable=create_task_lookup_agent(model),
        ),
        CompiledSubAgent(
            agent_id="task_creation",
            display_name="TaskCreationAgent",
            description=(
                "Create new one-off tasks with a deadline and optional details, priority, tags, "
                "or an explicitly requested schedule. Do not use for recurring work or changes "
                "to an existing task."
            ),
            runnable=create_task_creation_agent(model),
        ),
        CompiledSubAgent(
            agent_id="task_mutation",
            display_name="TaskMutationAgent",
            description=(
                "Change existing task records, including materialized recurring tasks: edit "
                "fields or deadlines, complete, reopen, cancel, attach or remove tags, and "
                "remove schedules. Prefer ScheduleAgent when time selection or conflicts are "
                "the main concern; do not use for recurrence templates, rules, or future "
                "occurrence overrides."
            ),
            runnable=create_task_mutation_agent(model),
        ),
        CompiledSubAgent(
            agent_id="tag",
            display_name="TagAgent",
            description=(
                "Manage tags as catalog entries: list, inspect, create or ensure, rename, and "
                "review tag history. Use when the tag itself is the main subject, not merely "
                "when assigning a tag to a task or recurring template."
            ),
            runnable=create_tag_agent(model),
        ),
        CompiledSubAgent(
            agent_id="schedule",
            display_name="ScheduleAgent",
            description=(
                "Manage planned time for existing ordinary tasks: inspect availability and "
                "conflicts, find free or nearest suitable time, and set, replace, or remove a "
                "task schedule. A schedule is a work window, not a deadline or a recurring-rule "
                "schedule."
            ),
            runnable=create_schedule_agent(model),
        ),
        CompiledSubAgent(
            agent_id="recurrence_template_lookup",
            display_name="RecurrenceTemplateLookupAgent",
            description=(
                "Read reusable recurring-task templates: find, list, count, inspect their tags "
                "and attached recurrence rules, and review template history. Do not use for "
                "ordinary tasks or for one specific planned occurrence."
            ),
            runnable=create_recurrence_template_lookup_agent(model),
        ),
        CompiledSubAgent(
            agent_id="recurrence_template_creation",
            display_name="RecurrenceTemplateCreationAgent",
            description=(
                "Create a new recurring-task template together with its initial recurrence "
                "rules, schedules, limits, priority, and tags. Use only for new recurring work, "
                "not for adding or changing rules on an existing template."
            ),
            runnable=create_recurrence_template_creation_agent(model),
        ),
        CompiledSubAgent(
            agent_id="recurrence_template_mutation",
            display_name="RecurrenceTemplateMutationAgent",
            description=(
                "Change the composition of an existing recurring-task template by attaching or "
                "removing template tags and, when part of that template-level change, adding or "
                "stopping rules. Use TaskRecurrenceRuleAgent when the recurrence rule itself is "
                "the main subject, especially when changing its parameters."
            ),
            runnable=create_recurrence_template_mutation_agent(model),
        ),
        CompiledSubAgent(
            agent_id="task_recurrence_rule",
            display_name="TaskRecurrenceRuleAgent",
            description=(
                "Manage recurrence rules on an existing template: add a cadence or schedule, "
                "change a rule's schedule or end condition, or stop a rule from a chosen time. "
                "Do not use for template tags or for changing one individual occurrence."
            ),
            runnable=create_task_recurrence_rule_agent(model),
        ),
        CompiledSubAgent(
            agent_id="task_occurrence",
            display_name="TaskOccurrenceAgent",
            description=(
                "Manage one planned run as a recurrence occurrence: find it by rule and original "
                "time, apply a per-occurrence override, or skip it, including before it is "
                "materialized. Do not use for normal field or status changes to an already "
                "materialized task, or for changing its template or recurrence rule."
            ),
            runnable=create_task_occurrence_agent(model),
        ),
    )
