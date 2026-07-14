from uuid import UUID

from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from dto.users import UpdateUserData
from domain.users import normalize_name, normalize_optional_name
from domain.value_objects.users import User


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    email: EmailStr | None = None

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
        if all(
            value is None
            for value in (self.first_name, self.last_name, self.middle_name, self.email)
        ):
            raise ValueError("at least one user field must be provided")
        return self

    def to_dto(self) -> UpdateUserData:
        return UpdateUserData(
            first_name=self.first_name,
            last_name=self.last_name,
            middle_name=self.middle_name,
            email=str(self.email) if self.email is not None else None,
        )


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    first_name: str
    last_name: str
    email: str
    middle_name: str | None

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        return cls(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            middle_name=user.middle_name,
        )
