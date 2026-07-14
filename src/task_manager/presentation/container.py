from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from agents.app import AgentApplication
from services.auth import AuthService
from services.chats import ChatService
from services.tags import TagService
from services.tasks import TaskService
from services.users import UserService
from adapters.unitofwork import SQLAlchemyUnitOfWork
from presentation.agent_stream import AgentStreamCoordinator


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Long-lived resources shared by HTTP requests in one server process."""

    engine: AsyncEngine
    uow: SQLAlchemyUnitOfWork
    auth_service: AuthService
    user_service: UserService
    task_service: TaskService
    tag_service: TagService
    chat_service: ChatService
    agent: AgentApplication
    agent_stream: AgentStreamCoordinator
    coordination_client: Redis
