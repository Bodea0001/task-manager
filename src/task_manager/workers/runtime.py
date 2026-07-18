from types import TracebackType
from typing import Self

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from config import CeleryConfig, DatabaseConfig, KeyValueStoreConfig
from services.tasks import TaskService
from adapters.background_job_coordination import RedisBackgroundJobCoordinator
from adapters.key_value_store import create_key_value_store_client
from adapters.unitofwork import SQLAlchemyUnitOfWork
from db.database import create_database_engine
from workers.coordination import BackgroundJobCoordinator


class WorkerRuntime:
    """Own async infrastructure resources for one Celery task invocation."""

    def __init__(
        self,
        database_config: DatabaseConfig,
        celery_config: CeleryConfig,
        key_value_store_config: KeyValueStoreConfig,
    ) -> None:
        self._database_config = database_config
        self._celery_config = celery_config
        self._key_value_store_config = key_value_store_config
        self._engine: AsyncEngine | None = None
        self._key_value_store_client: Redis | None = None
        self._task_service: TaskService | None = None
        self._job_coordinator: BackgroundJobCoordinator | None = None

    @property
    def task_service(self) -> TaskService:
        if self._task_service is None:
            raise RuntimeError("Worker runtime has not been entered")
        return self._task_service

    @property
    def job_coordinator(self) -> BackgroundJobCoordinator:
        if self._job_coordinator is None:
            raise RuntimeError("Worker runtime has not been entered")
        return self._job_coordinator

    async def __aenter__(self) -> Self:
        if self._engine is not None:
            raise RuntimeError("Worker runtime cannot be entered twice")

        worker_database_config = self._database_config.model_copy(
            update={
                "pool_size": self._celery_config.worker_db_pool_size,
                "max_overflow": 0,
            }
        )
        engine = create_database_engine(worker_database_config)
        key_value_store_client = create_key_value_store_client(
            self._key_value_store_config,
            max_connections=self._celery_config.coordination_max_connections,
        )
        try:
            task_service = TaskService(
                SQLAlchemyUnitOfWork(engine),
                recurrence_materialization_batch_size=(
                    self._celery_config.recurrence_materialization_batch_size
                ),
            )
            job_coordinator = RedisBackgroundJobCoordinator(
                key_value_store_client,
                self._celery_config,
            )
        except BaseException:
            await key_value_store_client.aclose()
            await engine.dispose()
            raise

        self._engine = engine
        self._key_value_store_client = key_value_store_client
        self._task_service = task_service
        self._job_coordinator = job_coordinator
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        key_value_store_client = self._key_value_store_client
        engine = self._engine
        self._key_value_store_client = None
        self._engine = None
        self._task_service = None
        self._job_coordinator = None

        if key_value_store_client is None or engine is None:
            return
        try:
            await key_value_store_client.aclose()
        finally:
            await engine.dispose()
