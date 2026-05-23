from pathlib import Path

from pydantic import BaseModel
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
    jwt_secret: str = "dev-only-change-me-with-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    password_salt: str = "dev-only-password-salt"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    refresh_token_session_limit: int = 5


class RecurrenceConfig(BaseModel):
    daily_materialization_days: int = 90
    weekly_materialization_days: int = 90
    monthly_materialization_days: int = 365


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        env_prefix=ENV_PREFIX,
    )

    db: DatabaseConfig
    auth: AuthConfig = AuthConfig()
    recurrence: RecurrenceConfig = RecurrenceConfig()


settings = Settings()  # type: ignore
