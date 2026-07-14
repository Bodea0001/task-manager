from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class HealthStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: HealthStatus
