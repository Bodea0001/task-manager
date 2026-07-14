from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Safe field-level validation detail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location: tuple[str | int, ...]
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Stable machine-readable HTTP error contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    request_id: str
    details: tuple[ErrorDetail, ...] = Field(default=())
