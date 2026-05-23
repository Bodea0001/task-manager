from uuid import UUID
from typing import Any, Concatenate, ParamSpec, TypeVar
from datetime import UTC, datetime
from dataclasses import asdict
from collections.abc import Awaitable, Callable
from functools import wraps

import asyncpg
from sqlalchemy import select, insert, update
from sqlalchemy.exc import IntegrityError, NoResultFound

import exceptions as app_exc
from dto.users import RegisterUser, UpdateUserData
from models.users import User as UserModel, UserAuth as UserAuthModel
from models.users import UserRefreshToken as UserRefreshTokenModel
from domain.value_objects.users import User, RefreshTokenSession
from adapters.repository import SQLAlchemyRepository


USER_EMAIL_CONSTRAINT = "uq_user_email"
REFRESH_TOKEN_HASH_CONSTRAINT = "uq_user_refresh_token_token_hash"
P = ParamSpec("P")
R = TypeVar("R")


def translate_repository_errors(
    method: Callable[Concatenate["UserRepository", P], Awaitable[R]],
) -> Callable[Concatenate["UserRepository", P], Awaitable[R]]:
    @wraps(method)
    async def wrapper(self: "UserRepository", /, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await method(self, *args, **kwargs)
        except NoResultFound:
            raise app_exc.UserNotFound
        except IntegrityError as e:
            self._raise_app_error_for_integrity_error(e)
            raise e

    return wrapper


class UserRepository(SQLAlchemyRepository):
    @translate_repository_errors
    async def add_user(self, data: RegisterUser) -> User:
        stmt = (
            insert(UserModel)
            .values(
                email=data.email,
                first_name=data.first_name,
                middle_name=data.middle_name,
                last_name=data.last_name,
            )
            .returning(UserModel)
        )

        result = await self.session.execute(stmt)
        user_model = result.scalar_one()
        await self.session.execute(
            insert(UserAuthModel).values(
                user_id=user_model.user_id,
                hashed_password=data.hashed_password,
            )
        )
        return self._model_to_user(user_model)

    @translate_repository_errors
    async def get_user(self, user_id: UUID) -> User:
        stmt = select(UserModel).where(UserModel.user_id == user_id)

        result = await self.session.execute(stmt)
        return self._model_to_user(result.scalar_one())

    @translate_repository_errors
    async def get_user_by_email(self, email: str) -> User:
        stmt = select(UserModel).where(UserModel.email == email)

        result = await self.session.execute(stmt)
        return self._model_to_user(result.scalar_one())

    async def get_hashed_password_by_email(self, email: str) -> str | None:
        stmt = (
            select(UserAuthModel.hashed_password)
            .join(UserModel, UserModel.user_id == UserAuthModel.user_id)
            .where(UserModel.email == email)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    @translate_repository_errors
    async def update_user(self, user_id: UUID, data: UpdateUserData) -> User:
        values = self._user_update_values(data)

        stmt = (
            update(UserModel)
            .values(**values)
            .where(UserModel.user_id == user_id)
            .returning(UserModel)
        )

        result = await self.session.execute(stmt)
        return self._model_to_user(result.scalar_one())

    async def add_refresh_token(
        self,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshTokenSession:
        stmt = (
            insert(UserRefreshTokenModel)
            .values(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            .returning(UserRefreshTokenModel)
        )

        result = await self.session.execute(stmt)
        return self._model_to_refresh_token_session(result.scalar_one())

    async def get_active_refresh_token(
        self,
        token_hash: str,
        now: datetime,
    ) -> RefreshTokenSession | None:
        stmt = select(UserRefreshTokenModel).where(
            UserRefreshTokenModel.token_hash == token_hash,
            UserRefreshTokenModel.revoked_at.is_(None),
            UserRefreshTokenModel.expires_at > now,
        )

        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None

        return self._model_to_refresh_token_session(model)

    async def revoke_refresh_token(self, token_hash: str) -> None:
        stmt = (
            update(UserRefreshTokenModel)
            .values(revoked_at=datetime.now(UTC))
            .where(
                UserRefreshTokenModel.token_hash == token_hash,
                UserRefreshTokenModel.revoked_at.is_(None),
            )
        )

        await self.session.execute(stmt)

    async def revoke_oldest_active_refresh_tokens(
        self,
        user_id: UUID,
        keep_count: int,
        now: datetime,
    ) -> None:
        if keep_count < 1:
            keep_count = 1

        token_hashes_to_revoke_stmt = (
            select(UserRefreshTokenModel.token_hash)
            .where(
                UserRefreshTokenModel.user_id == user_id,
                UserRefreshTokenModel.revoked_at.is_(None),
                UserRefreshTokenModel.expires_at > now,
            )
            .order_by(
                UserRefreshTokenModel.created_at.desc(),
                UserRefreshTokenModel.token_id.desc(),
            )
            .offset(keep_count)
        )

        result = await self.session.execute(token_hashes_to_revoke_stmt)
        token_hashes_to_revoke = result.scalars().all()

        if not token_hashes_to_revoke:
            return

        stmt = (
            update(UserRefreshTokenModel)
            .values(revoked_at=now)
            .where(UserRefreshTokenModel.token_hash.in_(token_hashes_to_revoke))
        )

        await self.session.execute(stmt)

    @staticmethod
    def _user_update_values(data: UpdateUserData) -> dict[str, Any]:
        return {k: v for k, v in asdict(data).items() if v is not None}

    @staticmethod
    def _model_to_user(model: UserModel) -> User:
        return User(
            user_id=model.user_id,
            first_name=model.first_name,
            middle_name=model.middle_name,
            last_name=model.last_name,
            email=model.email,
        )

    @staticmethod
    def _model_to_refresh_token_session(model: UserRefreshTokenModel) -> RefreshTokenSession:
        return RefreshTokenSession(
            token_id=model.token_id,
            user_id=model.user_id,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
        )

    @staticmethod
    def _raise_app_error_for_integrity_error(error: IntegrityError) -> None:
        driver_exc = getattr(error.orig, "__cause__", None)

        if isinstance(driver_exc, asyncpg.exceptions.UniqueViolationError):
            str_error = str(error.orig)

            if USER_EMAIL_CONSTRAINT in str_error:
                raise app_exc.EmailAlreadyExists

            if REFRESH_TOKEN_HASH_CONSTRAINT in str_error:
                raise app_exc.InvalidToken
