from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import true, Index, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import Uuid, Text, Enum, String, Boolean

from models.base import Base
from models.dependencies import created_at, uuidpk
from domain.value_objects.chats import ChatMessageRole

if TYPE_CHECKING:
    from models.users import User


class Chat(Base):
    __tablename__ = "chat"

    chat_id: Mapped[uuidpk]
    title: Mapped[str] = mapped_column(
        String(250),
        server_default="New chat",
        comment="Название чата",
    )
    creator_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id"),
        nullable=False,
        comment="Идентификатор создателя чата",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        comment="Признак активного чата пользователя",
    )
    created_at: Mapped[created_at]

    creator: Mapped["User"] = relationship("User", back_populates="created_chats")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="chat",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_chat_creator_id", "creator_id"),
        Index(
            "ix_chat_active_creator_id_unique",
            "creator_id",
            unique=True,
            postgresql_where=is_active.is_(True),
        ),
    )


class ChatMessage(Base):
    __tablename__ = "chat_message"

    message_id: Mapped[uuidpk]
    chat_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("chat.chat_id", ondelete="CASCADE"),
        nullable=False,
        comment="Идентификатор чата",
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        Enum(
            ChatMessageRole,
            name="chatmessagerole",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        comment="Роль автора сообщения",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст сообщения")
    created_at: Mapped[created_at]

    chat: Mapped[Chat] = relationship("Chat", back_populates="messages")

    __table_args__ = (
        CheckConstraint("length(content) > 0", "non_empty_content"),
        Index(
            "ix_chat_message_chat_id_created_at",
            "chat_id",
            "created_at",
            "message_id",
        ),
    )
