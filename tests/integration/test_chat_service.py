from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from constants import TEST_OTHER_USER_ID, TEST_USER_ID
from dto.chats import (
    AddChatMessage,
    CreateChatData,
    ListChatMessages,
    ListChats,
    UpdateChatData,
)
from domain.value_objects.chats import Chat, ChatMessageRole
from exceptions import ChatNotFound
from services.chats import ChatService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_user_can_create_chat(chat_service: ChatService) -> None:
    # Act
    sut = await chat_service.create_chat(TEST_USER_ID)

    # Assert
    assert sut.chat_id is not None
    assert sut.creator_id == TEST_USER_ID
    assert sut.title == "New chat"
    assert sut.is_active
    assert sut.created_at is not None


@pytest.mark.asyncio
async def test_user_can_create_and_rename_chat(chat_service: ChatService) -> None:
    chat = await chat_service.create_chat(
        TEST_USER_ID,
        CreateChatData(title="Release planning"),
    )

    sut = await chat_service.update_chat(
        TEST_USER_ID,
        chat.chat_id,
        UpdateChatData(title="Q3 release planning"),
    )

    assert chat.title == "Release planning"
    assert sut.title == "Q3 release planning"
    assert await chat_service.get_chat(TEST_USER_ID, chat.chat_id) == sut


@pytest.mark.asyncio
async def test_user_can_get_active_chat(chat_service: ChatService) -> None:
    # Arrange
    chat = await chat_service.create_chat(TEST_USER_ID)

    # Act
    sut = await chat_service.get_active_chat(TEST_USER_ID)

    # Assert
    assert sut == chat


@pytest.mark.asyncio
async def test_user_gets_empty_chat_list_when_no_chats_exist(chat_service: ChatService) -> None:
    # Act
    sut = await chat_service.get_chats(TEST_USER_ID)

    # Assert
    assert sut.items == ()
    assert sut.next_offset is None


@pytest.mark.asyncio
async def test_user_can_list_own_chats(chat_service: ChatService) -> None:
    # Arrange
    first = await chat_service.create_chat(TEST_USER_ID)
    second = await chat_service.create_chat(TEST_USER_ID)

    # Act
    sut = await chat_service.get_chats(TEST_USER_ID)

    # Assert
    assert [chat.chat_id for chat in sut.items] == [second.chat_id, first.chat_id]
    assert [chat.is_active for chat in sut.items] == [True, False]


@pytest.mark.asyncio
async def test_user_chat_list_excludes_another_users_chats(chat_service: ChatService) -> None:
    # Arrange
    own_chat = await chat_service.create_chat(TEST_USER_ID)
    other_chat = await chat_service.create_chat(TEST_OTHER_USER_ID)

    # Act
    sut = await chat_service.get_chats(TEST_USER_ID)

    # Assert
    assert chat_ids(sut.items) == {own_chat.chat_id}
    assert other_chat.chat_id not in chat_ids(sut.items)


@pytest.mark.asyncio
async def test_creating_chat_makes_it_the_only_active_chat(chat_service: ChatService) -> None:
    # Arrange
    first = await chat_service.create_chat(TEST_USER_ID)
    second = await chat_service.create_chat(TEST_USER_ID)

    # Act
    sut = await chat_service.get_active_chat(TEST_USER_ID)
    first_after_second = await chat_service.get_chat(TEST_USER_ID, first.chat_id)

    # Assert
    assert sut == second
    assert first_after_second.chat_id == first.chat_id
    assert not first_after_second.is_active


@pytest.mark.asyncio
async def test_user_can_activate_own_chat(chat_service: ChatService) -> None:
    # Arrange
    first = await chat_service.create_chat(TEST_USER_ID)
    second = await chat_service.create_chat(TEST_USER_ID)

    # Act
    sut = await chat_service.activate_chat(TEST_USER_ID, first.chat_id)
    second_after_activation = await chat_service.get_chat(TEST_USER_ID, second.chat_id)

    # Assert
    assert sut.chat_id == first.chat_id
    assert sut.is_active
    assert not second_after_activation.is_active
    assert await chat_service.get_active_chat(TEST_USER_ID) == sut


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ("get_chat", "activate_chat", "check_user_can_use_chat", "delete_chat"),
)
async def test_user_cannot_act_on_another_users_chat(
    chat_service: ChatService,
    action: str,
) -> None:
    # Arrange
    chat = await chat_service.create_chat(TEST_OTHER_USER_ID)

    # Act / Assert
    with pytest.raises(ChatNotFound):
        await getattr(chat_service, action)(TEST_USER_ID, chat.chat_id)

    await chat_service.check_user_can_use_chat(TEST_OTHER_USER_ID, chat.chat_id)


@pytest.mark.asyncio
async def test_missing_active_chat_is_not_found(chat_service: ChatService) -> None:
    # Act / Assert
    with pytest.raises(ChatNotFound):
        await chat_service.get_active_chat(TEST_USER_ID)


@pytest.mark.asyncio
async def test_user_can_use_own_chat(chat_service: ChatService) -> None:
    # Arrange
    chat = await chat_service.create_chat(TEST_USER_ID)

    # Act / Assert
    await chat_service.check_user_can_use_chat(TEST_USER_ID, chat.chat_id)


@pytest.mark.asyncio
async def test_user_can_read_chronological_chat_history(chat_service: ChatService) -> None:
    chat = await chat_service.create_chat(TEST_USER_ID)
    first = await chat_service.add_user_message(
        TEST_USER_ID,
        chat.chat_id,
        AddChatMessage(content="What is due today?"),
    )
    second = await chat_service.add_assistant_message(
        TEST_USER_ID,
        chat.chat_id,
        AddChatMessage(content="One task is due today."),
    )

    sut = await chat_service.get_chat_messages(TEST_USER_ID, chat.chat_id)
    newest_page = await chat_service.get_chat_messages(
        TEST_USER_ID,
        chat.chat_id,
        ListChatMessages(limit=1),
    )
    previous_page = await chat_service.get_chat_messages(
        TEST_USER_ID,
        chat.chat_id,
        ListChatMessages(limit=1, offset=1),
    )

    assert first.role is ChatMessageRole.USER
    assert second.role is ChatMessageRole.ASSISTANT
    assert sut.items == (first, second)
    assert newest_page.items == (second,)
    assert newest_page.next_offset == 1
    assert previous_page.items == (first,)
    assert previous_page.next_offset is None


@pytest.mark.asyncio
async def test_user_can_page_through_chats(chat_service: ChatService) -> None:
    first = await chat_service.create_chat(TEST_USER_ID, CreateChatData(title="First"))
    second = await chat_service.create_chat(TEST_USER_ID, CreateChatData(title="Second"))
    third = await chat_service.create_chat(TEST_USER_ID, CreateChatData(title="Third"))

    first_page = await chat_service.get_chats(TEST_USER_ID, ListChats(limit=2))
    second_page = await chat_service.get_chats(
        TEST_USER_ID,
        ListChats(limit=2, offset=2),
    )

    assert [chat.chat_id for chat in first_page.items] == [third.chat_id, second.chat_id]
    assert first_page.next_offset == 2
    assert [chat.chat_id for chat in second_page.items] == [first.chat_id]
    assert second_page.next_offset is None


@pytest.mark.asyncio
async def test_empty_chat_history_pages_are_not_missing_chat(
    chat_service: ChatService,
) -> None:
    chat = await chat_service.create_chat(TEST_USER_ID)

    page = await chat_service.get_chat_messages(TEST_USER_ID, chat.chat_id)

    assert page.items == ()
    assert page.next_offset is None


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_chat_history(
    chat_service: ChatService,
) -> None:
    chat = await chat_service.create_chat(TEST_OTHER_USER_ID)

    with pytest.raises(ChatNotFound):
        await chat_service.add_user_message(
            TEST_USER_ID,
            chat.chat_id,
            AddChatMessage(content="Private message"),
        )

    with pytest.raises(ChatNotFound):
        await chat_service.get_chat_messages(TEST_USER_ID, chat.chat_id)

    with pytest.raises(ChatNotFound):
        await chat_service.update_chat(
            TEST_USER_ID,
            chat.chat_id,
            UpdateChatData(title="Foreign title"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ("get_chat", "activate_chat", "check_user_can_use_chat", "delete_chat"),
)
async def test_user_cannot_act_on_missing_chat(
    chat_service: ChatService,
    action: str,
) -> None:
    # Act / Assert
    with pytest.raises(ChatNotFound):
        await getattr(chat_service, action)(TEST_USER_ID, uuid4())


@pytest.mark.asyncio
async def test_user_can_delete_own_chat(chat_service: ChatService) -> None:
    # Arrange
    chat = await chat_service.create_chat(TEST_USER_ID)

    # Act
    await chat_service.delete_chat(TEST_USER_ID, chat.chat_id)

    # Assert
    with pytest.raises(ChatNotFound):
        await chat_service.check_user_can_use_chat(TEST_USER_ID, chat.chat_id)


@pytest.mark.asyncio
async def test_deleting_active_chat_removes_active_chat(chat_service: ChatService) -> None:
    # Arrange
    chat = await chat_service.create_chat(TEST_USER_ID)

    # Act
    await chat_service.delete_chat(TEST_USER_ID, chat.chat_id)

    # Assert
    with pytest.raises(ChatNotFound):
        await chat_service.get_active_chat(TEST_USER_ID)


@pytest.mark.asyncio
async def test_deleting_chat_cascades_to_its_messages(
    chat_service: ChatService,
    test_engine: AsyncEngine,
) -> None:
    chat = await chat_service.create_chat(TEST_USER_ID)
    message = await chat_service.add_user_message(
        TEST_USER_ID,
        chat.chat_id,
        AddChatMessage(content="Temporary message"),
    )

    await chat_service.delete_chat(TEST_USER_ID, chat.chat_id)

    async with test_engine.connect() as connection:
        message_count = await connection.scalar(
            text("SELECT count(*) FROM chat_message WHERE message_id = :message_id"),
            {"message_id": message.message_id},
        )
    assert message_count == 0


def chat_ids(chats: tuple[Chat, ...]) -> set:
    return {chat.chat_id for chat in chats}
