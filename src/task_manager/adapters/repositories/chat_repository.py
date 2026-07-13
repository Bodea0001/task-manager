from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import aliased

import exceptions as app_exc
from dto.chats import AddChatMessage, CreateChatData, ListChatMessages, ListChats, UpdateChatData
from models.chats import Chat as ChatModel, ChatMessage as ChatMessageModel
from adapters.repository import SQLAlchemyRepository
from domain.value_objects.chats import (
    Chat,
    ChatMessage,
    ChatMessagePage,
    ChatMessageRole,
    ChatPage,
)


class ChatRepository(SQLAlchemyRepository):
    async def add_chat(self, user_id: UUID, data: CreateChatData) -> Chat:
        stmt = insert(ChatModel).values(creator_id=user_id, title=data.title).returning(ChatModel)

        result = await self.session.execute(stmt)
        return self._model_to_chat(result.scalar_one())

    async def get_active_chat(self, user_id: UUID) -> Chat:
        stmt = select(ChatModel).where(
            ChatModel.creator_id == user_id,
            ChatModel.is_active.is_(True),
        )

        result = await self.session.execute(stmt)
        try:
            return self._model_to_chat(result.scalar_one())
        except NoResultFound:
            raise app_exc.ChatNotFound

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        stmt = select(ChatModel).where(
            ChatModel.creator_id == user_id,
            ChatModel.chat_id == chat_id,
        )

        result = await self.session.execute(stmt)
        try:
            return self._model_to_chat(result.scalar_one())
        except NoResultFound:
            raise app_exc.ChatNotFound

    async def get_chats(self, user_id: UUID, filters: ListChats) -> ChatPage:
        stmt = (
            select(ChatModel)
            .where(ChatModel.creator_id == user_id)
            .order_by(ChatModel.created_at.desc())
            .limit(filters.limit + 1)
            .offset(filters.offset)
        )

        result = await self.session.execute(stmt)
        chats = [self._model_to_chat(chat) for chat in result.scalars()]
        next_offset = self._get_next_offset(len(chats), filters.limit, filters.offset)
        items = chats[: filters.limit]
        return ChatPage(tuple(items), next_offset)

    async def update_chat(self, chat_id: UUID, data: UpdateChatData) -> Chat:
        stmt = (
            update(ChatModel)
            .values(title=data.title)
            .where(ChatModel.chat_id == chat_id)
            .returning(ChatModel)
        )
        result = await self.session.execute(stmt)
        try:
            return self._model_to_chat(result.scalar_one())
        except NoResultFound:
            raise app_exc.ChatNotFound

    async def add_message(
        self,
        chat_id: UUID,
        role: ChatMessageRole,
        data: AddChatMessage,
    ) -> ChatMessage:
        stmt = (
            insert(ChatMessageModel)
            .values(chat_id=chat_id, role=role, content=data.content)
            .returning(ChatMessageModel)
        )
        result = await self.session.execute(stmt)
        return self._model_to_chat_message(result.scalar_one())

    async def get_messages(
        self,
        chat_id: UUID,
        filters: ListChatMessages,
    ) -> ChatMessagePage:
        message_page_cte = (
            select(ChatMessageModel)
            .where(ChatMessageModel.chat_id == chat_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(filters.limit + 1)
            .offset(filters.offset)
            .cte("message_page")
        )
        message_page = aliased(ChatMessageModel, message_page_cte)
        stmt = select(message_page).order_by(message_page.created_at.asc())

        result = await self.session.execute(stmt)
        messages = [self._model_to_chat_message(message) for message in result.scalars()]
        next_offset = self._get_next_offset(len(messages), filters.limit, filters.offset)
        items = messages[-filters.limit :]
        return ChatMessagePage(tuple(items), next_offset)

    async def exists_chat(self, user_id: UUID, chat_id: UUID) -> bool:
        stmt = select(
            select(1)
            .select_from(ChatModel)
            .where(ChatModel.creator_id == user_id, ChatModel.chat_id == chat_id)
            .exists()
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> None:
        stmt = delete(ChatModel).where(
            ChatModel.creator_id == user_id,
            ChatModel.chat_id == chat_id,
        )

        await self.session.execute(stmt)

    async def activate_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        stmt = (
            update(ChatModel)
            .values(is_active=True)
            .where(ChatModel.creator_id == user_id, ChatModel.chat_id == chat_id)
            .returning(ChatModel)
        )

        result = await self.session.execute(stmt)
        try:
            return self._model_to_chat(result.scalar_one())
        except NoResultFound:
            raise app_exc.ChatNotFound

    @staticmethod
    def _model_to_chat(model: ChatModel) -> Chat:
        return Chat(
            chat_id=model.chat_id,
            creator_id=model.creator_id,
            title=model.title,
            is_active=model.is_active,
            created_at=model.created_at,
        )

    @staticmethod
    def _model_to_chat_message(model: ChatMessageModel) -> ChatMessage:
        return ChatMessage(
            message_id=model.message_id,
            chat_id=model.chat_id,
            role=model.role,
            content=model.content,
            created_at=model.created_at,
        )

    @staticmethod
    def _get_next_offset(result_count: int, limit: int, offset: int) -> int | None:
        return offset + limit if result_count > limit else None
