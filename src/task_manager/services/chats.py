from uuid import UUID

import exceptions as app_exc
from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.value_objects.chats import Chat


class ChatService:
    """Application service for agent chat sessions and user chat isolation."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def create_chat(self, user_id: UUID) -> Chat:
        async with self.uow() as uow:
            return await uow.chat.add_chat(user_id)

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        async with self.uow(read_only=True) as uow:
            await self._check_if_chat_exists(uow, user_id, chat_id)
            return await uow.chat.get_chat(user_id, chat_id)

    async def get_chats(self, user_id: UUID) -> list[Chat]:
        async with self.uow(read_only=True) as uow:
            return await uow.chat.get_chats(user_id)

    async def get_active_chat(self, user_id: UUID) -> Chat:
        async with self.uow(read_only=True) as uow:
            return await uow.chat.get_active_chat(user_id)

    async def activate_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        async with self.uow() as uow:
            await self._check_if_chat_exists(uow, user_id, chat_id)
            return await uow.chat.activate_chat(user_id, chat_id)

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_chat_exists(uow, user_id, chat_id)
            await uow.chat.delete_chat(user_id, chat_id)

    async def check_user_can_use_chat(self, user_id: UUID, chat_id: UUID) -> None:
        async with self.uow(read_only=True) as uow:
            await self._check_if_chat_exists(uow, user_id, chat_id)

    @staticmethod
    async def _check_if_chat_exists(uow, user_id: UUID, chat_id: UUID) -> None:
        if not await uow.chat.exists_chat(user_id, chat_id):
            raise app_exc.ChatNotFound
