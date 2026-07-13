from uuid import UUID

import exceptions as app_exc
from dto.chats import (
    AddChatMessage,
    CreateChatData,
    ListChatMessages,
    ListChats,
    UpdateChatData,
)
from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.value_objects.chats import (
    Chat,
    ChatMessage,
    ChatMessagePage,
    ChatMessageRole,
    ChatPage,
)


class ChatService:
    """Application service for agent chat sessions and user chat isolation."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def create_chat(self, user_id: UUID, data: CreateChatData | None = None) -> Chat:
        data = data or CreateChatData()
        async with self.uow() as uow:
            return await uow.chat.add_chat(user_id, data)

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        async with self.uow(read_only=True) as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)
            return await uow.chat.get_chat(user_id, chat_id)

    async def get_chats(
        self,
        user_id: UUID,
        filters: ListChats | None = None,
    ) -> ChatPage:
        """Return chats ordered by creation using bounded pagination."""
        filters = filters or ListChats()
        async with self.uow(read_only=True) as uow:
            return await uow.chat.get_chats(user_id, filters)

    async def update_chat(self, user_id: UUID, chat_id: UUID, data: UpdateChatData) -> Chat:
        async with self.uow() as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)
            return await uow.chat.update_chat(chat_id, data)

    async def add_user_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: AddChatMessage,
    ) -> ChatMessage:
        """Append a user-authored message without accepting a caller-supplied role."""
        return await self._add_chat_message(user_id, chat_id, ChatMessageRole.USER, data)

    async def add_assistant_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: AddChatMessage,
    ) -> ChatMessage:
        """Append a trusted assistant response to a user-owned chat."""
        return await self._add_chat_message(user_id, chat_id, ChatMessageRole.ASSISTANT, data)

    async def _add_chat_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        role: ChatMessageRole,
        data: AddChatMessage,
    ) -> ChatMessage:
        async with self.uow() as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)
            return await uow.chat.add_message(chat_id, role, data)

    async def get_chat_messages(
        self,
        user_id: UUID,
        chat_id: UUID,
        filters: ListChatMessages | None = None,
    ) -> ChatMessagePage:
        """Return one chronological page from the user-visible chat history."""
        filters = filters or ListChatMessages()
        async with self.uow(read_only=True) as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)
            return await uow.chat.get_messages(chat_id, filters)

    async def get_active_chat(self, user_id: UUID) -> Chat:
        async with self.uow(read_only=True) as uow:
            return await uow.chat.get_active_chat(user_id)

    async def activate_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        async with self.uow() as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)
            return await uow.chat.activate_chat(user_id, chat_id)

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)
            await uow.chat.delete_chat(user_id, chat_id)

    async def check_user_can_use_chat(self, user_id: UUID, chat_id: UUID) -> None:
        async with self.uow(read_only=True) as uow:
            await self._check_user_can_access_chat(uow, user_id, chat_id)

    @staticmethod
    async def _check_user_can_access_chat(uow, user_id: UUID, chat_id: UUID) -> None:
        if not await uow.chat.exists_chat(user_id, chat_id):
            raise app_exc.ChatNotFound
