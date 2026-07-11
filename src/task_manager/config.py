from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, SecretStr
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
    recurrence: RecurrenceConfig = RecurrenceConfig()


settings = Settings()  # type: ignore
