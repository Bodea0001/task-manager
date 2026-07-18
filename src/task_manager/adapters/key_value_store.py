from redis.asyncio import Redis

from config import KeyValueStoreConfig


def create_key_value_store_client(
    config: KeyValueStoreConfig,
    max_connections: int,
) -> Redis:
    """Create a process-local client for the shared key-value store."""
    return Redis.from_url(
        config.url,
        max_connections=max_connections,
        socket_connect_timeout=config.connect_timeout_seconds,
        socket_timeout=config.socket_timeout_seconds,
        health_check_interval=config.health_check_interval_seconds,
        decode_responses=True,
    )
