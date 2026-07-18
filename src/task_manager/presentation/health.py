from asyncio import timeout

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


DATABASE_HEALTH_TIMEOUT_SECONDS = 2
KEY_VALUE_STORE_HEALTH_TIMEOUT_SECONDS = 2


async def is_database_ready(engine: AsyncEngine) -> bool:
    """Return whether PostgreSQL answers a bounded lightweight query."""
    try:
        async with timeout(DATABASE_HEALTH_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except TimeoutError, SQLAlchemyError:
        return False
    return True


async def is_key_value_store_ready(client: Redis) -> bool:
    """Return whether the shared key-value store answers a bounded command."""
    try:
        async with timeout(KEY_VALUE_STORE_HEALTH_TIMEOUT_SECONDS):
            await client.ping()
    except TimeoutError, RedisError:
        return False
    return True
