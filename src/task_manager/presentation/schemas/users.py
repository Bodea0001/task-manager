from uuid import UUID

from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_validator,
    model_validator,
)

from dto.users import UpdateUserData
from domain.users import normalize_name, normalize_optional_name
from domain.value_objects.users import User
from domain.value_objects.agent_usage import AgentAccessLevel, AgentRunAllowance


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_required_name(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        field_name = info.field_name
        if field_name is None:
            raise ValueError("name field is not available")
        return normalize_name(value, field_name)

    @field_validator("middle_name")
    @classmethod
    def validate_middle_name(cls, value: str | None) -> str | None:
        normalize_optional_name(value, "middle_name")
        return value

    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one user field must be provided")

        for field_name in ("first_name", "last_name"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self

    def to_dto(self) -> UpdateUserData:
        return UpdateUserData(
            first_name=self.first_name,
            last_name=self.last_name,
            middle_name=self.middle_name,
            clear_middle_name=("middle_name" in self.model_fields_set and self.middle_name is None),
        )


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    first_name: str
    last_name: str
    email: str
    middle_name: str | None
    email_verified: bool

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        return cls(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            middle_name=user.middle_name,
            email_verified=user.email_verified,
        )


class AgentRunAllowanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    used: int
    access_level: AgentAccessLevel
    limit: int | None
    remaining: int | None

    @classmethod
    def from_domain(cls, allowance: AgentRunAllowance) -> "AgentRunAllowanceResponse":
        return cls(
            used=allowance.used,
            access_level=allowance.access_level,
            limit=allowance.limit,
            remaining=allowance.remaining,
        )
