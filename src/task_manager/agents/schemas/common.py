from uuid import UUID
from enum import StrEnum
from typing import Any, cast, Annotated, TypedDict, Required, NotRequired
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field
from langgraph.channels import DeltaChannel
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langgraph.channels.ephemeral_value import EphemeralValue
from langchain.agents.middleware.types import JumpTo, OmitFromInput, PrivateStateAttr

from services.tags import TagService
from services.tasks import TaskService


class AgentStatus(StrEnum):
    """Final task-agent execution status."""

    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"


class AgentContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    user_id: UUID = Field(
        description="Authenticated user id from trusted application context.",
    )
    task_service: TaskService = Field(
        description="Application task service scoped by tools with the trusted user id.",
    )
    tag_service: TagService = Field(
        description="Application tag service scoped by tools with the trusted user id.",
    )


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AgentStatus = Field(
        description="Structured outcome of the agent run.",
    )
    message: str = Field(
        description="User-facing answer produced by the agent.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured data used by callers for follow-up flows.",
    )


def _messages_reducer(state: Sequence[BaseMessage], writes: Sequence[Any]) -> list[BaseMessage]:
    messages = list(state)
    for write in writes:
        messages = add_messages(cast(Any, messages), write)
    return cast(list[BaseMessage], messages)


class AgentState(TypedDict):
    messages: Required[Annotated[Sequence[BaseMessage], DeltaChannel(_messages_reducer)]]
    jump_to: NotRequired[Annotated[JumpTo | None, EphemeralValue, PrivateStateAttr]]
    selected_tool_profile: NotRequired[Annotated[str, OmitFromInput]]
    structured_response: NotRequired[Annotated[AgentResult, OmitFromInput]]
