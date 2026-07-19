from services.users import UserService
from adapters.unitofwork import SQLAlchemyUnitOfWork
from db.database import create_database_engine

from config import settings


class CliRuntime:
    """Own application dependencies shared by commands in one CLI invocation."""

    def __init__(self) -> None:
        db_config = settings.db.model_copy(update={"pool_size": 1, "max_overflow": 0})
        self._engine = create_database_engine(db_config)
        self.user_service = UserService(SQLAlchemyUnitOfWork(self._engine))

    async def close(self) -> None:
        await self._engine.dispose()
