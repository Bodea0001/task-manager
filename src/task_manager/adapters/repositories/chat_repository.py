from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import NoResultFound

import exceptions as app_exc
from models.chats import Chat as ChatModel
from adapters.repository import SQLAlchemyRepository
from domain.value_objects.chats import Chat


class ChatRepository(SQLAlchemyRepository):
    async def add_chat(self, user_id: UUID) -> Chat:
        stmt = insert(ChatModel).values(creator_id=user_id).returning(ChatModel)

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

    async def get_chats(self, user_id: UUID) -> list[Chat]:
        stmt = (
            select(ChatModel)
            .where(ChatModel.creator_id == user_id)
            .order_by(ChatModel.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return [self._model_to_chat(chat) for chat in result.scalars()]

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
            is_active=model.is_active,
            created_at=model.created_at,
        )
