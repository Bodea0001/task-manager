from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_PREFIX = "TASK_CONFIG_"
ENV_NESTED_DELIMITER = "_"

_PROJECT_PATH = Path(__file__).resolve().parents[2]


# конфиг для базы данных
class DatabaseConfig(BaseModel):
    database: str = "postgresql"
    driver: str = "asyncpg"
    host: str = "localhost"
    port: int = 5432
    user: str
    password: str
    name: str
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout_seconds: float = Field(default=30.0, gt=0)

    @property
    def url(self) -> str:
        return f"{self.database}+{self.driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class AuthConfig(BaseModel):
    jwt_secret: str
    password_salt: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    refresh_token_session_limit: int = 5


class RecurrenceConfig(BaseModel):
    daily_materialization_days: int = 90
    weekly_materialization_days: int = 90
    monthly_materialization_days: int = 365


class KeyValueStoreConfig(BaseModel):
    """Connection settings for the shared Redis-compatible key-value store."""

    model_config = ConfigDict(extra="forbid")

    url: str = "redis://localhost:6379/0"
    connect_timeout_seconds: float = Field(default=1.0, gt=0)
    socket_timeout_seconds: float = Field(default=1.0, gt=0)
    health_check_interval_seconds: int = Field(default=30, ge=0)


class CeleryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker_pool_limit: int = Field(default=2, ge=1)
    broker_key_prefix: str = Field(default="task-manager:v1:celery:", min_length=1)
    result_backend: str | None = None
    coordination_key_prefix: str = "task-manager:v1:background-job"
    coordination_max_connections: int = Field(default=2, ge=1)
    lease_ttl_seconds: int = Field(default=2_400, ge=60)
    lease_renew_interval_seconds: int = Field(default=600, ge=1)
    completion_ttl_seconds: int = Field(default=604_800, ge=86_400)
    recurrence_materialization_queue: str = "recurrence_materialization"
    recurrence_materialization_hour: int = Field(default=2, ge=0, le=23)
    recurrence_materialization_minute: int = Field(default=0, ge=0, le=59)
    recurrence_materialization_batch_size: int = Field(default=20, ge=1, le=100)
    timezone: str = "UTC"
    message_expires_seconds: int = Field(default=72_000, ge=3_600, le=86_400)
    retry_max_retries: int = Field(default=4, ge=0, le=10)
    retry_backoff_seconds: int = Field(default=30, ge=1)
    retry_backoff_max_seconds: int = Field(default=900, ge=1)
    task_soft_time_limit_seconds: int = Field(default=1_800, ge=60)
    task_time_limit_seconds: int = Field(default=2_100, ge=60)
    worker_concurrency: int = Field(default=1, ge=1)
    worker_prefetch_multiplier: int = Field(default=1, ge=1)
    worker_db_pool_size: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_execution_timing(self) -> "CeleryConfig":
        if self.task_soft_time_limit_seconds >= self.task_time_limit_seconds:
            raise ValueError("task soft time limit must be shorter than hard time limit")
        if self.task_time_limit_seconds >= self.lease_ttl_seconds:
            raise ValueError("task hard time limit must be shorter than lease TTL")
        if self.lease_renew_interval_seconds >= self.lease_ttl_seconds:
            raise ValueError("lease renewal interval must be shorter than lease TTL")
        if self.retry_backoff_seconds > self.retry_backoff_max_seconds:
            raise ValueError("retry backoff must not exceed maximum retry backoff")
        if not self.timezone.strip():
            raise ValueError("Celery timezone cannot be empty")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Celery timezone must be a valid IANA timezone") from exc
        return self


class CoordinationConfig(BaseModel):
    """Agent-run coordination settings independent of the backing store."""

    key_prefix: str = "task-manager:v1:agent-run"
    max_connections: int = Field(default=10, ge=1)
    lease_ttl_seconds: int = Field(default=90, ge=10)
    lease_renew_interval_seconds: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def validate_lease_timing(self) -> "CoordinationConfig":
        if self.lease_renew_interval_seconds >= self.lease_ttl_seconds:
            raise ValueError("lease renewal interval must be shorter than lease TTL")
        return self


class HTTPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_prefix: str = "/api/v1"
    docs_enabled: bool = True
    cors_allowed_origins: tuple[str, ...] = ()
    trusted_hosts: tuple[str, ...] = ()

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value == "/" or value.endswith("/") or "//" in value:
            raise ValueError("api_prefix must be an absolute path without a trailing slash")
        return value


class AgentConfig(BaseModel):
    planner_model_name: str = Field(
        validation_alias=AliasChoices("planner_model_name", "base_model_name")
    )
    subagent_model_name: str = Field(
        validation_alias=AliasChoices("subagent_model_name", "base_model_name")
    )
    base_url: str
    base_api_key: SecretStr
    planner_thinking_mode: Literal["enabled", "disabled"] = "enabled"
    subagent_thinking_mode: Literal["enabled", "disabled"] = "disabled"
    model_timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    max_message_length: int = 4_000
    max_iterations: int = 75
    max_tool_calls: int = 20
    checkpoint_durability: Literal["sync", "async", "exit"] = "exit"
    summarization_trigger_messages: int = 25
    summarization_keep_messages: int = 10


class AgentUsageConfig(BaseModel):
    unverified_run_limit: int = Field(default=3, ge=1)
    verified_run_limit: int = Field(default=10, ge=1)
    reservation_ttl_seconds: int = Field(default=3_600, ge=300)

    @model_validator(mode="after")
    def validate_limits(self) -> "AgentUsageConfig":
        if self.verified_run_limit < self.unverified_run_limit:
            raise ValueError("verified agent run limit must not be lower than unverified limit")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        env_nested_max_split=1,
        env_prefix=ENV_PREFIX,
    )

    db: DatabaseConfig
    auth: AuthConfig
    agent: AgentConfig
    agent_usage: AgentUsageConfig = AgentUsageConfig()
    recurrence: RecurrenceConfig = RecurrenceConfig()
    key_value_store: KeyValueStoreConfig = KeyValueStoreConfig()
    celery: CeleryConfig = CeleryConfig()
    coordination: CoordinationConfig = CoordinationConfig()
    http: HTTPConfig = HTTPConfig()


settings = Settings()  # type: ignore
