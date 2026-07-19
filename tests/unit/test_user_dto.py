import pytest

from domain.auth import PasswordHasher
from dto.users import LoginUser, RegisterUser, UpdateUserData


def test_register_user_data_is_normalized() -> None:
    # Act
    data = RegisterUser(
        email="  User.Name@Example.COM ",
        password="correct-password",
        first_name="  First   Name  ",
        last_name="  Last   Name  ",
        middle_name="  Middle   Name  ",
    )

    # Assert
    assert data.email == "user.name@example.com"
    assert data.first_name == "First Name"
    assert data.last_name == "Last Name"
    assert data.middle_name == "Middle Name"
    assert not hasattr(data, "password")
    assert data.hashed_password


def test_register_user_stores_hashed_password() -> None:
    # Arrange
    password_hasher = PasswordHasher()
    data = RegisterUser(
        email="user@example.com",
        password="correct-password",
        first_name="First",
        last_name="Last",
        password_hasher=password_hasher,
    )

    # Assert
    assert password_hasher.verify_password("correct-password", data.hashed_password)


@pytest.mark.parametrize(
    "data",
    [
        {
            "email": "invalid-email",
            "password": "correct-password",
            "first_name": "First",
            "last_name": "Last",
        },
        {
            "email": "user@example.com",
            "password": "short",
            "first_name": "First",
            "last_name": "Last",
        },
        {
            "email": "user@example.com",
            "password": " correct-password",
            "first_name": "First",
            "last_name": "Last",
        },
        {
            "email": "user@example.com",
            "password": "correct-password",
            "first_name": "",
            "last_name": "Last",
        },
        {
            "email": "user@example.com",
            "password": "correct-password",
            "first_name": "First",
            "last_name": " ",
        },
        {
            "email": "x" * 309 + "@example.com",
            "password": "correct-password",
            "first_name": "First",
            "last_name": "Last",
        },
        {
            "email": "user@example.com",
            "password": "correct-password",
            "first_name": "x" * 251,
            "last_name": "Last",
        },
    ],
)
def test_register_user_with_invalid_data_is_rejected(data: dict) -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        RegisterUser(**data)


def test_login_user_email_is_normalized() -> None:
    # Act
    data = LoginUser(email="  User.Name@Example.COM ", password="correct-password")

    # Assert
    assert data.email == "user.name@example.com"
    assert data.password == "correct-password"


def test_user_update_data_is_normalized() -> None:
    # Act
    data = UpdateUserData(
        first_name="  Updated   First  ",
        last_name="  Updated   Last  ",
        middle_name="  Updated   Middle  ",
    )

    # Assert
    assert data.first_name == "Updated First"
    assert data.last_name == "Updated Last"
    assert data.middle_name == "Updated Middle"


def test_empty_user_update_is_rejected() -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        UpdateUserData()


def test_user_update_can_explicitly_clear_middle_name() -> None:
    data = UpdateUserData(clear_middle_name=True)

    assert data.middle_name is None
    assert data.clear_middle_name is True


@pytest.mark.parametrize(
    "data",
    [
        {"first_name": ""},
        {"first_name": " "},
        {"first_name": "x" * 251},
        {"last_name": ""},
        {"last_name": " "},
        {"last_name": "x" * 251},
        {"middle_name": "x" * 251},
    ],
)
def test_user_update_with_invalid_data_is_rejected(data: dict) -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        UpdateUserData(**data)
