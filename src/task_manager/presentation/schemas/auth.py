from pydantic import BaseModel, ConfigDict, SecretStr, ValidationInfo, field_validator, EmailStr

from dto.users import LoginUser, RegisterUser
from domain.users import normalize_name, validate_password, normalize_optional_name
from domain.value_objects.users import AuthTokens


class RegisterUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr
    first_name: str
    last_name: str
    middle_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_value(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_required_name(cls, value: str, info: ValidationInfo) -> str:
        field_name = info.field_name
        if field_name is None:
            raise ValueError("name field is not available")
        return normalize_name(value, field_name)

    @field_validator("middle_name")
    @classmethod
    def normalize_middle_name(cls, value: str | None) -> str | None:
        return normalize_optional_name(value, "middle_name")

    def to_dto(self) -> RegisterUser:
        return RegisterUser(
            email=self.email,
            password=self.password.get_secret_value(),
            first_name=self.first_name,
            last_name=self.last_name,
            middle_name=self.middle_name,
        )


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr

    def to_dto(self) -> LoginUser:
        return LoginUser(email=self.email, password=self.password.get_secret_value())


class AccessTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str
    token_type: str

    @classmethod
    def from_domain(cls, tokens: AuthTokens) -> "AccessTokenResponse":
        return cls(
            access_token=tokens.access_token,
            token_type=tokens.token_type,
        )
