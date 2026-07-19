from uuid import UUID
from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.types import String, Uuid, TIMESTAMP

from models.base import Base
from models.dependencies import created_at, uuidpk

if TYPE_CHECKING:
    from models.chats import Chat
    from models.tags import Tag
    from models.tasks import Task
    from models.agent_usage import UserAgentRunUsage


class User(Base):
    __tablename__ = "user"

    user_id: Mapped[uuidpk]
    first_name: Mapped[str] = mapped_column(String(250), comment="Имя пользователя")
    middle_name: Mapped[str | None] = mapped_column(
        String(250), nullable=True, comment="Отчество пользователя"
    )
    last_name: Mapped[str] = mapped_column(String(250), comment="Фамилия пользователя")
    email: Mapped[str] = mapped_column(String(320), comment="Email пользователя")

    auth: Mapped["UserAuth | None"] = relationship(
        "UserAuth", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    email_verification: Mapped["UserEmailVerification | None"] = relationship(
        "UserEmailVerification",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    agent_run_usage: Mapped[list["UserAgentRunUsage"]] = relationship(
        "UserAgentRunUsage", back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["UserRefreshToken"]] = relationship(
        "UserRefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    created_tasks: Mapped[list["Task"]] = relationship("Task", back_populates="creator")
    created_tags: Mapped[list["Tag"]] = relationship("Tag", back_populates="creator")
    created_chats: Mapped[list["Chat"]] = relationship(
        "Chat", back_populates="creator", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("length(first_name) > 0", "non_empty_first_name"),
        CheckConstraint("length(middle_name) > 0", "non_empty_middle_name"),
        CheckConstraint("length(last_name) > 0", "non_empty_last_name"),
        CheckConstraint("length(email) >= 6", "valid_email_length"),
        UniqueConstraint("email"),
    )


class UserAuth(Base):
    __tablename__ = "user_auth"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id"),
        primary_key=True,
        comment="Идентификатор пользователя",
    )
    hashed_password: Mapped[str] = mapped_column(String(255), comment="Хеш пароля пользователя")

    user: Mapped[User] = relationship("User", back_populates="auth")

    __table_args__ = (CheckConstraint("length(hashed_password) > 0", "non_empty_hashed_password"),)


class UserEmailVerification(Base):
    __tablename__ = "user_email_verification"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Идентификатор пользователя",
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Дата/время подтверждения email",
    )

    user: Mapped[User] = relationship("User", back_populates="email_verification")


class UserRefreshToken(Base):
    __tablename__ = "user_refresh_token"

    token_id: Mapped[uuidpk]
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.user_id"),
        index=True,
        comment="Идентификатор пользователя",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, comment="SHA-256 хеш refresh-токена"
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), comment="Дата/время истечения refresh-токена"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="Дата/время отзыва refresh-токена"
    )
    created_at: Mapped[created_at]

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (CheckConstraint("length(token_hash) = 64", "valid_token_hash_length"),)
