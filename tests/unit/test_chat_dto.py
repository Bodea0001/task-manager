import pytest

from dto.chats import (
    AddChatMessage,
    CreateChatData,
    ListChatMessages,
    ListChats,
    UpdateChatData,
)


def test_chat_input_is_normalized() -> None:
    chat = CreateChatData(title="  Release planning  ")
    update = UpdateChatData(title="  Q3 planning  ")
    message = AddChatMessage(content="  Hello  ")

    assert chat.title == "Release planning"
    assert update.title == "Q3 planning"
    assert message.content == "Hello"


@pytest.mark.parametrize("title", ("", "   ", "x" * 251))
def test_invalid_chat_title_is_rejected(title: str) -> None:
    with pytest.raises(ValueError):
        CreateChatData(title=title)


def test_empty_chat_message_is_rejected() -> None:
    with pytest.raises(ValueError):
        AddChatMessage(content="   ")


@pytest.mark.parametrize(
    "filters",
    (
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ),
)
def test_invalid_chat_page_size_is_rejected(filters: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ListChatMessages(**filters)

    with pytest.raises(ValueError):
        ListChats(**filters)
