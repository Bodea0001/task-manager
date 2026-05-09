from uuid import UUID
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

import exceptions as app_exc


class PasswordHasher:
    def __init__(
        self,
        password_hash: PasswordHash | None = None,
        password_salt: str = "",
    ) -> None:
        if password_hash is None:
            password_hash = PasswordHash.recommended()
        self._password_hash = password_hash
        self._password_salt = password_salt

    def hash_password(self, password: str) -> str:
        return self._password_hash.hash(self._salt_password(password))

    def verify_password(self, password: str, hashed_password: str) -> bool:
        return self._password_hash.verify(self._salt_password(password), hashed_password)

    def _salt_password(self, password: str) -> str:
        return f"{self._password_salt}{password}"


class JWTTokenService:
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str,
        access_token_ttl: timedelta,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_token_ttl = access_token_ttl

    def create_access_token(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + self._access_token_ttl,
            "type": "access",
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def get_user_id_from_access_token(self, token: str) -> UUID:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            if payload.get("type") != "access":
                raise app_exc.InvalidToken
            return UUID(payload["sub"])
        except jwt.PyJWTError, KeyError, TypeError, ValueError:
            raise app_exc.InvalidToken
