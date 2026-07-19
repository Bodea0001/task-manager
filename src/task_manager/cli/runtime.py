from services.users import UserService
from services.agent_usage import AgentUsageService
from adapters.unitofwork import SQLAlchemyUnitOfWork
from db.database import create_database_engine

from config import settings


class CliRuntime:
    """Own application dependencies shared by commands in one CLI invocation."""

    def __init__(self) -> None:
        db_config = settings.db.model_copy(update={"pool_size": 1, "max_overflow": 0})
        self._engine = create_database_engine(db_config)
        uow = SQLAlchemyUnitOfWork(self._engine)
        self.user_service = UserService(uow)
        self.agent_usage_service = AgentUsageService(uow)

    async def close(self) -> None:
        await self._engine.dispose()
