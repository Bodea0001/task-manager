from uuid import UUID
from datetime import datetime
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class User:
    user_id: UUID
    first_name: str
    last_name: str
    email: str
    email_verified: bool
    middle_name: str | None = None


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass(frozen=True, slots=True)
class RefreshTokenSession:
    token_id: UUID
    user_id: UUID
    expires_at: datetime
    revoked_at: datetime | None = None
