from typing import Any, cast, Annotated, TypedDict, Required, NotRequired
from collections.abc import Sequence

from langgraph.channels import DeltaChannel
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langgraph.channels.ephemeral_value import EphemeralValue
from langchain.agents.middleware.types import JumpTo, OmitFromInput, PrivateStateAttr

from agents.schemas.result import AgentResult
from agents.schemas.planning import AgentPlan


def _messages_reducer(state: Sequence[BaseMessage], writes: Sequence[Any]) -> list[BaseMessage]:
    messages = list(state)
    for write in writes:
        messages = add_messages(cast(Any, messages), write)
    return cast(list[BaseMessage], messages)


class AgentState(TypedDict):
    messages: Required[Annotated[Sequence[BaseMessage], DeltaChannel(_messages_reducer)]]
    jump_to: NotRequired[Annotated[JumpTo | None, EphemeralValue, PrivateStateAttr]]
    plan: NotRequired[Annotated[AgentPlan | None, OmitFromInput]]
    step_results: NotRequired[Annotated[dict[str, AgentResult], OmitFromInput]]
    structured_response: NotRequired[Annotated[AgentResult, OmitFromInput]]
