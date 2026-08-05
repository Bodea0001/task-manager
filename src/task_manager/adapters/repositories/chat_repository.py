from uuid import UUID

from sqlalchemy import delete, insert, literal, select, true, update
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

    async def add_user_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: AddChatMessage,
        response_attempt_id: UUID,
    ) -> tuple[ChatMessage, UUID | None]:
        owned_chat = (
            select(ChatModel.chat_id)
            .where(ChatModel.chat_id == chat_id, ChatModel.creator_id == user_id)
            .cte("owned_chat")
        )
        latest_message_id = (
            select(ChatMessageModel.message_id)
            .join(owned_chat, owned_chat.c.chat_id == ChatMessageModel.chat_id)
            .order_by(ChatMessageModel.created_at.desc(), ChatMessageModel.message_id.desc())
            .limit(1)
            .scalar_subquery()
        )
        preceding_unresolved = (
            update(ChatMessageModel)
            .where(
                ChatMessageModel.message_id == latest_message_id,
                ChatMessageModel.role == ChatMessageRole.USER,
            )
            .values(response_attempt_id=None)
            .returning(ChatMessageModel.message_id)
            .cte("preceding_unresolved_message")
        )
        inserted_message = (
            insert(ChatMessageModel)
            .from_select(
                ["chat_id", "role", "content", "response_attempt_id"],
                select(
                    owned_chat.c.chat_id,
                    literal(ChatMessageRole.USER, type_=ChatMessageModel.role.type),
                    literal(data.content),
                    literal(response_attempt_id),
                ),
            )
            .returning(ChatMessageModel)
            .cte("inserted_user_message")
        )
        message = aliased(ChatMessageModel, inserted_message)
        stmt = (
            select(
                message,
                preceding_unresolved.c.message_id.label("preceding_unresolved_message_id"),
            )
            .select_from(inserted_message)
            .outerjoin(preceding_unresolved, true())
        )

        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise app_exc.ChatNotFound
        return self._model_to_chat_message(row[0]), row[1]

    async def retry_last_user_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        response_attempt_id: UUID,
    ) -> ChatMessage:
        owned_chat = (
            select(ChatModel.chat_id)
            .where(ChatModel.chat_id == chat_id, ChatModel.creator_id == user_id)
            .cte("owned_chat")
        )
        latest_message_id = (
            select(ChatMessageModel.message_id)
            .join(owned_chat, owned_chat.c.chat_id == ChatMessageModel.chat_id)
            .order_by(ChatMessageModel.created_at.desc(), ChatMessageModel.message_id.desc())
            .limit(1)
            .scalar_subquery()
        )
        retried_message = (
            update(ChatMessageModel)
            .where(
                ChatMessageModel.message_id == latest_message_id,
                ChatMessageModel.role == ChatMessageRole.USER,
            )
            .values(response_attempt_id=response_attempt_id)
            .returning(ChatMessageModel)
            .cte("retried_user_message")
        )
        message = aliased(ChatMessageModel, retried_message)
        stmt = (
            select(owned_chat.c.chat_id, message)
            .select_from(owned_chat)
            .outerjoin(retried_message, true())
        )

        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise app_exc.ChatNotFound
        if not isinstance(row[1], ChatMessageModel):
            raise app_exc.AgentRequestNotRetryable
        return self._model_to_chat_message(row[1])

    async def add_assistant_message(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: AddChatMessage,
        response_attempt_id: UUID,
    ) -> ChatMessage:
        claimed_request = (
            update(ChatMessageModel)
            .where(
                ChatMessageModel.chat_id == chat_id,
                ChatMessageModel.response_attempt_id == response_attempt_id,
                ChatMessageModel.role == ChatMessageRole.USER,
                ChatMessageModel.chat_id.in_(
                    select(ChatModel.chat_id).where(ChatModel.creator_id == user_id)
                ),
            )
            .values(response_attempt_id=None)
            .returning(ChatMessageModel.chat_id)
            .cte("claimed_agent_request")
        )
        inserted_message = (
            insert(ChatMessageModel)
            .from_select(
                ["chat_id", "role", "content"],
                select(
                    claimed_request.c.chat_id,
                    literal(ChatMessageRole.ASSISTANT, type_=ChatMessageModel.role.type),
                    literal(data.content),
                ),
            )
            .returning(ChatMessageModel)
            .cte("inserted_assistant_message")
        )
        message = aliased(ChatMessageModel, inserted_message)
        stmt = select(message)

        result = await self.session.execute(stmt)
        try:
            return self._model_to_chat_message(result.scalar_one())
        except NoResultFound:
            raise app_exc.ChatNotFound from None

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
    def _model_to_chat_message(
        model: ChatMessageModel,
    ) -> ChatMessage:
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
