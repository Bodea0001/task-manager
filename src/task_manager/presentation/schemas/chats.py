from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from dto.chats import (
    CHAT_TITLE_MAX_LENGTH,
    DEFAULT_CHAT_TITLE,
    CreateChatData,
    ListChatMessages,
    ListChats,
    UpdateChatData,
)
from domain.value_objects.chats import (
    Chat,
    ChatMessage,
    ChatMessagePage,
    ChatMessageRole,
    ChatPage,
)


class CreateChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(
        default=DEFAULT_CHAT_TITLE,
        min_length=1,
        max_length=CHAT_TITLE_MAX_LENGTH,
    )

    def to_dto(self) -> CreateChatData:
        return CreateChatData(title=self.title)


class UpdateChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=CHAT_TITLE_MAX_LENGTH)

    def to_dto(self) -> UpdateChatData:
        return UpdateChatData(title=self.title)


class ChatListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    def to_dto(self) -> ListChats:
        return ListChats(limit=self.limit, offset=self.offset)


class ChatMessageListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    def to_dto(self) -> ListChatMessages:
        return ListChatMessages(limit=self.limit, offset=self.offset)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chat_id: UUID
    title: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_domain(cls, chat: Chat) -> "ChatResponse":
        return cls(
            chat_id=chat.chat_id,
            title=chat.title,
            is_active=chat.is_active,
            created_at=chat.created_at,
        )


class ChatListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chats: tuple[ChatResponse, ...]
    next_offset: int | None

    @classmethod
    def from_domain(cls, page: ChatPage) -> "ChatListResponse":
        return cls(
            chats=tuple(ChatResponse.from_domain(chat) for chat in page.items),
            next_offset=page.next_offset,
        )


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: UUID
    chat_id: UUID
    role: ChatMessageRole
    content: str
    created_at: datetime

    @classmethod
    def from_domain(cls, message: ChatMessage) -> "ChatMessageResponse":
        return cls(
            message_id=message.message_id,
            chat_id=message.chat_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )


class ChatMessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: tuple[ChatMessageResponse, ...]
    next_offset: int | None

    @classmethod
    def from_domain(cls, page: ChatMessagePage) -> "ChatMessageListResponse":
        return cls(
            messages=tuple(ChatMessageResponse.from_domain(message) for message in page.items),
            next_offset=page.next_offset,
        )
