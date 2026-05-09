from types import TracebackType
from typing import Self
from logging import getLogger

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncConnection,
    AsyncTransaction,
    async_sessionmaker,
)

from domain.value_objects.isolation_level import IsolationLevel
from adapters.repositories.tag_repository import TagRepository
from adapters.repositories.task_repository import TaskRepository
from adapters.repositories.user_repository import UserRepository


logger = getLogger(__name__)


class SQLAlchemyUnitOfWork:
    """Creates transactional SQLAlchemy async sessions for application use cases."""

    def __init__(
        self,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._engine = engine

        if not session_maker:
            session_maker = async_sessionmaker(bind=self._engine, expire_on_commit=False)
        self._session_maker = session_maker

    def __call__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
        read_only: bool = False,
    ) -> "_TransactionContext":
        logger.debug(
            "Creating transaction context: isolation_level=%r read_only=%s",
            isolation_level.value,
            read_only,
        )
        return _TransactionContext(
            engine=self._engine,
            session_maker=self._session_maker,
            isolation_level=isolation_level,
            read_only=read_only,
        )


class _TransactionContext:
    """Async transaction scope returned by SQLAlchemyUnitOfWork."""

    def __init__(
        self,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        isolation_level: IsolationLevel,
        read_only: bool,
    ) -> None:
        self._engine = engine
        self._session_maker = session_maker
        self._isolation_level = isolation_level
        self._read_only = read_only
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        logger.debug(
            "Opening transaction: isolation_level=%r read_only=%s",
            self._isolation_level.value,
            self._read_only,
        )
        self._connection = await self._open_connection()
        self._transaction = await self._connection.begin()
        self.session = self._session_maker(bind=self._connection)

        self._initialize_repositories()

        logger.debug("Transaction opened")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type:
                logger.exception(
                    "Transaction failed, rolling back",
                    exc_info=(exc_type, exc, tb),  # type: ignore
                )
                await self.rollback()
            else:
                await self.commit()
        finally:
            await self._close()

    async def commit(self) -> None:
        assert self._transaction is not None
        logger.debug("Committing transaction")
        await self._transaction.commit()
        logger.debug("Transaction committed")

    async def rollback(self) -> None:
        assert self._transaction is not None
        logger.debug("Rolling back transaction")
        await self._transaction.rollback()
        logger.debug("Transaction rolled back")

    async def _open_connection(self) -> AsyncConnection:
        connection = await self._engine.connect()
        return await connection.execution_options(
            isolation_level=self._isolation_level,
            postgresql_read_only=self._read_only,
        )

    def _initialize_repositories(self):
        assert self.session is not None
        logger.debug("Initializing repositories")
        self.tag = TagRepository(self.session)
        self.task = TaskRepository(self.session)
        self.user = UserRepository(self.session)
        logger.debug("Repositories initialized")

    async def _close(self) -> None:
        assert self.session is not None
        assert self._connection is not None
        logger.debug("Closing transaction resources")
        await self.session.close()
        await self._connection.close()
        logger.debug("Transaction resources closed")
