from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config import DatabaseConfig, settings

DB_URL = settings.db.url


def create_database_engine(config: DatabaseConfig | None = None) -> AsyncEngine:
    """Create an application-owned SQLAlchemy engine."""
    database_config = config or settings.db

    return create_async_engine(
        url=database_config.url,
        pool_size=database_config.pool_size,
        max_overflow=database_config.max_overflow,
        pool_timeout=database_config.pool_timeout_seconds,
    )
