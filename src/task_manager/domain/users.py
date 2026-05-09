import re


EMAIL_MAX_LENGTH = 320
NAME_MAX_LENGTH = 250
PASSWORD_MIN_LENGTH = 8
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    normalized_email = email.strip().lower()
    validate_email(normalized_email)
    return normalized_email


def normalize_name(name: str, field_name: str) -> str:
    normalized_name = " ".join(name.strip().split())
    validate_required_text(normalized_name, field_name, NAME_MAX_LENGTH)
    return normalized_name


def normalize_optional_name(name: str | None, field_name: str) -> str | None:
    if name is None:
        return None

    normalized_name = " ".join(name.strip().split())
    if not normalized_name:
        return None

    validate_required_text(normalized_name, field_name, NAME_MAX_LENGTH)
    return normalized_name


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password cannot be shorter than {PASSWORD_MIN_LENGTH} characters")

    if password.strip() != password:
        raise ValueError("password cannot start or end with whitespace")


def validate_email(email: str) -> None:
    if not email:
        raise ValueError("email cannot be empty")

    if len(email) > EMAIL_MAX_LENGTH:
        raise ValueError(f"email cannot be longer than {EMAIL_MAX_LENGTH} characters")

    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("email must be valid")


def validate_required_text(value: str, field_name: str, max_length: int) -> None:
    if not value:
        raise ValueError(f"{field_name} cannot be empty")

    if len(value) > max_length:
        raise ValueError(f"{field_name} cannot be longer than {max_length} characters")
