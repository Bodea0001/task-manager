from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import true, Index, ForeignKey
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import Uuid, Boolean

from models.base import Base
from models.dependencies import created_at, uuidpk

if TYPE_CHECKING:
    from models.users import User


class Chat(Base):
    __tablename__ = "chat"

    chat_id: Mapped[uuidpk]
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

    __table_args__ = (
        Index("ix_chat_creator_id", "creator_id"),
        Index(
            "ix_chat_active_creator_id_unique",
            "creator_id",
            unique=True,
            postgresql_where=is_active.is_(True),
        ),
    )
