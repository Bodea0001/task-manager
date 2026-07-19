import os
from dataclasses import InitVar, dataclass, field

from domain.auth import PasswordHasher
from domain.users import (
    normalize_email,
    normalize_name,
    validate_password,
    normalize_optional_name,
)


DEFAULT_PASSWORD_SALT = "dev-only-password-salt"
PASSWORD_SALT_ENV = "TASK_CONFIG_AUTH_PASSWORD_SALT"


@dataclass(frozen=True, slots=True)
class RegisterUser:
    email: str
    password: InitVar[str]
    first_name: str
    last_name: str
    middle_name: str | None = None
    password_hasher: InitVar[PasswordHasher | None] = None
    hashed_password: str = field(init=False, default="", repr=False)

    def __post_init__(self, password: str, password_hasher: PasswordHasher | None) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
        object.__setattr__(self, "first_name", normalize_name(self.first_name, "first_name"))
        object.__setattr__(self, "last_name", normalize_name(self.last_name, "last_name"))
        object.__setattr__(
            self,
            "middle_name",
            normalize_optional_name(self.middle_name, "middle_name"),
        )
        validate_password(password)
        if password_hasher is None:
            password_hasher = PasswordHasher(
                password_salt=os.getenv(PASSWORD_SALT_ENV, DEFAULT_PASSWORD_SALT)
            )
        object.__setattr__(self, "hashed_password", password_hasher.hash_password(password))


@dataclass(frozen=True, slots=True)
class LoginUser:
    email: str
    password: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))


@dataclass(frozen=True, slots=True)
class UpdateUserData:
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    clear_middle_name: bool = False

    def __post_init__(self) -> None:
        if (
            all(value is None for value in (self.first_name, self.last_name, self.middle_name))
            and not self.clear_middle_name
        ):
            raise ValueError("at least one user field must be provided")

        if self.middle_name is not None and self.clear_middle_name:
            raise ValueError("middle_name cannot be updated and cleared together")

        if self.first_name is not None:
            object.__setattr__(self, "first_name", normalize_name(self.first_name, "first_name"))
        if self.last_name is not None:
            object.__setattr__(self, "last_name", normalize_name(self.last_name, "last_name"))
        if self.middle_name is not None:
            object.__setattr__(
                self,
                "middle_name",
                normalize_optional_name(self.middle_name, "middle_name"),
            )
