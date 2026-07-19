from dataclasses import dataclass

from domain.users import normalize_email
from domain.value_objects.agent_usage import AgentAccessLevel


@dataclass(frozen=True, slots=True)
class SetAgentAccessData:
    email: str
    access_level: AgentAccessLevel

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
