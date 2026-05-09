from uuid import uuid4
from datetime import timedelta

import jwt
import pytest

from domain.auth import JWTTokenService, PasswordHasher
from exceptions import InvalidToken


JWT_SECRET = "test-secret-with-at-least-32-bytes"
JWT_ALGORITHM = "HS256"


def test_password_hasher_verifies_password_with_same_salt() -> None:
    # Arrange
    hasher = PasswordHasher(password_salt="first-salt")
    hashed_password = hasher.hash_password("correct-password")

    # Act / Assert
    assert hasher.verify_password("correct-password", hashed_password)


def test_password_hasher_rejects_password_with_different_salt() -> None:
    # Arrange
    first_hasher = PasswordHasher(password_salt="first-salt")
    second_hasher = PasswordHasher(password_salt="second-salt")
    hashed_password = first_hasher.hash_password("correct-password")

    # Act / Assert
    assert not second_hasher.verify_password("correct-password", hashed_password)


def test_jwt_token_service_extracts_user_id_from_access_token() -> None:
    # Arrange
    user_id = uuid4()
    token_service = JWTTokenService(
        secret=JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        access_token_ttl=timedelta(minutes=5),
    )

    # Act
    token = token_service.create_access_token(user_id)

    # Assert
    assert token_service.get_user_id_from_access_token(token) == user_id


def test_expired_access_token_is_rejected() -> None:
    # Arrange
    user_id = uuid4()
    token_service = JWTTokenService(
        secret=JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        access_token_ttl=timedelta(seconds=-1),
    )
    token = token_service.create_access_token(user_id)

    # Act / Assert
    with pytest.raises(InvalidToken):
        token_service.get_user_id_from_access_token(token)


@pytest.mark.parametrize(
    "payload",
    [
        {"sub": str(uuid4()), "type": "refresh"},
        {"type": "access"},
        {"sub": "not-a-uuid", "type": "access"},
    ],
)
def test_access_token_with_invalid_payload_is_rejected(payload: dict) -> None:
    # Arrange
    token_service = JWTTokenService(
        secret=JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        access_token_ttl=timedelta(minutes=5),
    )
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Act / Assert
    with pytest.raises(InvalidToken):
        token_service.get_user_id_from_access_token(token)


def test_malformed_access_token_is_rejected() -> None:
    # Arrange
    token_service = JWTTokenService(
        secret=JWT_SECRET,
        algorithm=JWT_ALGORITHM,
        access_token_ttl=timedelta(minutes=5),
    )

    # Act / Assert
    with pytest.raises(InvalidToken):
        token_service.get_user_id_from_access_token("not-a-token")
