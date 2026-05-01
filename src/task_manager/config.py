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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        env_prefix=ENV_PREFIX,
    )

    db: DatabaseConfig


settings = Settings()  # type: ignore
