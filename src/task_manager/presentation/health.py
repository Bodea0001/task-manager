from asyncio import timeout

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


DATABASE_HEALTH_TIMEOUT_SECONDS = 2
COORDINATION_HEALTH_TIMEOUT_SECONDS = 2


async def is_database_ready(engine: AsyncEngine) -> bool:
    """Return whether PostgreSQL answers a bounded lightweight query."""
    try:
        async with timeout(DATABASE_HEALTH_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except TimeoutError, SQLAlchemyError:
        return False
    return True


async def is_coordination_ready(client: Redis) -> bool:
    """Return whether Redis answers a bounded lightweight command."""
    try:
        async with timeout(COORDINATION_HEALTH_TIMEOUT_SECONDS):
            await client.ping()
    except TimeoutError, RedisError:
        return False
    return True
