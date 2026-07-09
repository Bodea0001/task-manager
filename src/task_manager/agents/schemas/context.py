from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.tags import TagService
from services.tasks import TaskService


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
