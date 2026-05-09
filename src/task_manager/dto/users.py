from dataclasses import dataclass

from domain.users import (
    normalize_email,
    normalize_name,
    validate_password,
    normalize_optional_name,
)


@dataclass(frozen=True, slots=True)
class RegisterUser:
    email: str
    password: str
    first_name: str
    last_name: str
    middle_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
        object.__setattr__(self, "first_name", normalize_name(self.first_name, "first_name"))
        object.__setattr__(self, "last_name", normalize_name(self.last_name, "last_name"))
        object.__setattr__(
            self,
            "middle_name",
            normalize_optional_name(self.middle_name, "middle_name"),
        )
        validate_password(self.password)


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
    email: str | None = None

    def __post_init__(self) -> None:
        if all(
            value is None
            for value in (self.first_name, self.last_name, self.middle_name, self.email)
        ):
            raise ValueError("at least one user field must be provided")

        if self.email is not None:
            object.__setattr__(self, "email", normalize_email(self.email))
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
