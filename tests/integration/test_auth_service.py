from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from constants import TEST_USER_ID
from adapters.unitofwork import SQLAlchemyUnitOfWork
from dto.users import LoginUser, RegisterUser, UpdateUserData
from dto.users import VerifyUserEmailData
from exceptions import (
    EmailAlreadyExists,
    EmailVerificationRequired,
    InvalidCredentials,
    InvalidToken,
)
from services.auth import AuthService
from services.users import UserService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_get_own_profile(user_service: UserService) -> None:
    user = await user_service.get_user(TEST_USER_ID)

    assert user.user_id == TEST_USER_ID
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_email_verification_requirement_tracks_account_state(
    auth_service: AuthService,
    user_service: UserService,
) -> None:
    tokens = await auth_service.register(
        RegisterUser(
            email="verification-policy@example.com",
            password="correct-password",
            first_name="Verification",
            last_name="Policy",
        )
    )
    user = await auth_service.get_current_user(tokens.access_token)

    with pytest.raises(EmailVerificationRequired):
        await user_service.require_email_verified(user.user_id)

    await user_service.verify_user_email(VerifyUserEmailData("verification-policy@example.com"))

    await user_service.require_email_verified(user.user_id)


@pytest.mark.asyncio
async def test_user_can_register_and_get_current_user(auth_service: AuthService) -> None:
    # Arrange
    data = RegisterUser(
        email="  New.User@Example.COM ",
        password="correct-password",
        first_name="  New  ",
        last_name="  User  ",
    )

    # Act
    tokens = await auth_service.register(data)
    current_user = await auth_service.get_current_user(tokens.access_token)

    # Assert
    assert tokens.token_type == "bearer"
    assert tokens.access_token
    assert tokens.refresh_token
    assert current_user.email == "new.user@example.com"
    assert current_user.email_verified is False
    assert current_user.first_name == "New"
    assert current_user.last_name == "User"


@pytest.mark.asyncio
async def test_trusted_administration_can_verify_user_email(
    auth_service: AuthService,
    user_service: UserService,
) -> None:
    tokens = await auth_service.register(
        RegisterUser(
            email="admin-verified@example.com",
            password="correct-password",
            first_name="Admin",
            last_name="Verified",
        )
    )

    verified_user = await user_service.verify_user_email(
        VerifyUserEmailData(" ADMIN-VERIFIED@example.com ")
    )
    current_user = await auth_service.get_current_user(tokens.access_token)

    assert verified_user.email_verified is True
    assert current_user.email_verified is True


@pytest.mark.asyncio
async def test_user_cannot_register_with_existing_email(auth_service: AuthService) -> None:
    # Arrange
    data = RegisterUser(
        email="duplicate@example.com",
        password="correct-password",
        first_name="Duplicate",
        last_name="User",
    )
    await auth_service.register(data)

    # Act / Assert
    with pytest.raises(EmailAlreadyExists):
        await auth_service.register(data)


@pytest.mark.asyncio
async def test_user_can_login(auth_service: AuthService) -> None:
    # Arrange
    await auth_service.register(
        RegisterUser(
            email="login@example.com",
            password="correct-password",
            first_name="Login",
            last_name="User",
        )
    )

    # Act
    tokens = await auth_service.login(
        LoginUser(email=" LOGIN@example.com ", password="correct-password")
    )
    current_user = await auth_service.get_current_user(tokens.access_token)

    # Assert
    assert current_user.email == "login@example.com"


@pytest.mark.asyncio
async def test_user_cannot_login_with_wrong_password(auth_service: AuthService) -> None:
    # Arrange
    await auth_service.register(
        RegisterUser(
            email="wrong-password@example.com",
            password="correct-password",
            first_name="Login",
            last_name="User",
        )
    )

    # Act / Assert
    with pytest.raises(InvalidCredentials):
        await auth_service.login(
            LoginUser(email="wrong-password@example.com", password="wrong-password")
        )


@pytest.mark.asyncio
async def test_user_cannot_login_with_unknown_email(auth_service: AuthService) -> None:
    # Act / Assert
    with pytest.raises(InvalidCredentials):
        await auth_service.login(
            LoginUser(email="unknown-login@example.com", password="correct-password")
        )


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_used_as_access_token(auth_service: AuthService) -> None:
    # Arrange
    tokens = await auth_service.register(
        RegisterUser(
            email="refresh-as-access@example.com",
            password="correct-password",
            first_name="Refresh",
            last_name="AsAccess",
        )
    )

    # Act / Assert
    with pytest.raises(InvalidToken):
        await auth_service.get_current_user(tokens.refresh_token)


@pytest.mark.asyncio
async def test_user_can_refresh_tokens(auth_service: AuthService) -> None:
    # Arrange
    tokens = await auth_service.register(
        RegisterUser(
            email="refresh@example.com",
            password="correct-password",
            first_name="Refresh",
            last_name="User",
        )
    )

    # Act
    refreshed_tokens = await auth_service.refresh(tokens.refresh_token)

    # Assert
    current_user = await auth_service.get_current_user(refreshed_tokens.access_token)
    assert current_user.email == "refresh@example.com"
    assert refreshed_tokens.refresh_token != tokens.refresh_token


@pytest.mark.asyncio
async def test_user_can_revoke_refresh_session(auth_service: AuthService) -> None:
    # Arrange
    tokens = await auth_service.register(
        RegisterUser(
            email="logout@example.com",
            password="correct-password",
            first_name="Logout",
            last_name="User",
        )
    )

    # Act
    await auth_service.revoke_refresh_token(tokens.refresh_token)
    await auth_service.revoke_refresh_token(tokens.refresh_token)

    # Assert
    with pytest.raises(InvalidToken):
        await auth_service.refresh(tokens.refresh_token)


@pytest.mark.asyncio
async def test_malformed_refresh_token_is_rejected(auth_service: AuthService) -> None:
    # Act / Assert
    with pytest.raises(InvalidToken):
        await auth_service.refresh("not-a-refresh-token")


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(test_engine: AsyncEngine) -> None:
    # Arrange
    auth_service = AuthService(
        SQLAlchemyUnitOfWork(test_engine),
        refresh_token_ttl=timedelta(seconds=-1),
    )
    tokens = await auth_service.register(
        RegisterUser(
            email="expired-refresh@example.com",
            password="correct-password",
            first_name="Expired",
            last_name="Refresh",
        )
    )

    # Act / Assert
    with pytest.raises(InvalidToken):
        await auth_service.refresh(tokens.refresh_token)


@pytest.mark.asyncio
async def test_refresh_token_is_rotated(auth_service: AuthService) -> None:
    # Arrange
    tokens = await auth_service.register(
        RegisterUser(
            email="rotate@example.com",
            password="correct-password",
            first_name="Rotate",
            last_name="User",
        )
    )
    await auth_service.refresh(tokens.refresh_token)

    # Act / Assert
    with pytest.raises(InvalidToken):
        await auth_service.refresh(tokens.refresh_token)


@pytest.mark.asyncio
async def test_user_can_keep_multiple_refresh_sessions(auth_service: AuthService) -> None:
    # Arrange
    first_session_tokens = await auth_service.register(
        RegisterUser(
            email="multi-session@example.com",
            password="correct-password",
            first_name="Multi",
            last_name="Session",
        )
    )
    second_session_tokens = await auth_service.login(
        LoginUser(email="multi-session@example.com", password="correct-password")
    )

    # Act
    refreshed_first_session_tokens = await auth_service.refresh(first_session_tokens.refresh_token)
    refreshed_second_session_tokens = await auth_service.refresh(
        second_session_tokens.refresh_token
    )

    # Assert
    first_session_user = await auth_service.get_current_user(
        refreshed_first_session_tokens.access_token
    )
    second_session_user = await auth_service.get_current_user(
        refreshed_second_session_tokens.access_token
    )
    assert first_session_user.user_id == second_session_user.user_id


@pytest.mark.asyncio
async def test_oldest_refresh_session_is_revoked_when_session_limit_is_exceeded(
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    auth_service = AuthService(SQLAlchemyUnitOfWork(test_engine), refresh_token_session_limit=2)
    first_session_tokens = await auth_service.register(
        RegisterUser(
            email="limited-sessions@example.com",
            password="correct-password",
            first_name="Limited",
            last_name="Sessions",
        )
    )
    second_session_tokens = await auth_service.login(
        LoginUser(email="limited-sessions@example.com", password="correct-password")
    )
    third_session_tokens = await auth_service.login(
        LoginUser(email="limited-sessions@example.com", password="correct-password")
    )

    # Act / Assert
    with pytest.raises(InvalidToken):
        await auth_service.refresh(first_session_tokens.refresh_token)

    refreshed_second_session_tokens = await auth_service.refresh(
        second_session_tokens.refresh_token
    )
    refreshed_third_session_tokens = await auth_service.refresh(third_session_tokens.refresh_token)
    second_session_user = await auth_service.get_current_user(
        refreshed_second_session_tokens.access_token
    )
    third_session_user = await auth_service.get_current_user(
        refreshed_third_session_tokens.access_token
    )
    assert second_session_user.user_id == third_session_user.user_id


@pytest.mark.asyncio
async def test_user_can_update_profile(
    auth_service: AuthService,
    user_service: UserService,
) -> None:
    # Arrange
    tokens = await auth_service.register(
        RegisterUser(
            email="profile@example.com",
            password="correct-password",
            first_name="Old",
            last_name="Name",
        )
    )
    current_user = await auth_service.get_current_user(tokens.access_token)

    # Act
    updated_user = await user_service.update_user(
        current_user.user_id,
        UpdateUserData(
            first_name="  Updated  ",
            last_name="  Profile  ",
            middle_name="  Middle  ",
        ),
    )

    # Assert
    assert updated_user.email == "profile@example.com"
    assert updated_user.first_name == "Updated"
    assert updated_user.last_name == "Profile"
    assert updated_user.middle_name == "Middle"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("update_data", "field_name", "expected_value"),
    (
        (UpdateUserData(first_name="OnlyFirst"), "first_name", "OnlyFirst"),
        (UpdateUserData(last_name="OnlyLast"), "last_name", "OnlyLast"),
        (UpdateUserData(middle_name="OnlyMiddle"), "middle_name", "OnlyMiddle"),
    ),
)
async def test_user_can_update_profile_partially(
    auth_service: AuthService,
    user_service: UserService,
    update_data: UpdateUserData,
    field_name: str,
    expected_value: str,
) -> None:
    # Arrange
    tokens = await auth_service.register(
        RegisterUser(
            email=f"partial-{field_name}@example.com",
            password="correct-password",
            first_name="Partial",
            last_name="Update",
        )
    )
    current_user = await auth_service.get_current_user(tokens.access_token)

    # Act
    updated_user = await user_service.update_user(current_user.user_id, update_data)

    # Assert
    assert getattr(updated_user, field_name) == expected_value


@pytest.mark.asyncio
async def test_user_can_clear_middle_name(
    auth_service: AuthService,
    user_service: UserService,
) -> None:
    tokens = await auth_service.register(
        RegisterUser(
            email="clear-middle-name@example.com",
            password="correct-password",
            first_name="Clear",
            last_name="Name",
            middle_name="Middle",
        )
    )
    current_user = await auth_service.get_current_user(tokens.access_token)

    updated_user = await user_service.update_user(
        current_user.user_id,
        UpdateUserData(clear_middle_name=True),
    )

    assert updated_user.middle_name is None
