from uuid import UUID
from enum import StrEnum
from datetime import datetime
from dataclasses import dataclass


class ChatMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Chat:
    chat_id: UUID
    creator_id: UUID
    title: str
    is_active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ChatMessage:
    message_id: UUID
    chat_id: UUID
    role: ChatMessageRole
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ChatPage:
    items: tuple[Chat, ...]
    next_offset: int | None


@dataclass(frozen=True, slots=True)
class ChatMessagePage:
    items: tuple[ChatMessage, ...]
    next_offset: int | None
