from datetime import UTC, datetime, timedelta

import exceptions as app_exc
from dto.users import LoginUser, RegisterUser
from domain.auth import JWTTokenService, PasswordHasher
from domain.value_objects.users import AuthTokens, User
from domain.refresh_tokens import create_refresh_token, hash_refresh_token
from adapters.unitofwork import SQLAlchemyUnitOfWork

from config import settings


class AuthService:
    def __init__(
        self,
        uow: SQLAlchemyUnitOfWork,
        password_hasher: PasswordHasher | None = None,
        token_service: JWTTokenService | None = None,
        refresh_token_ttl: timedelta | None = None,
        refresh_token_session_limit: int | None = None,
    ) -> None:
        self.uow = uow
        self.password_hasher = password_hasher or PasswordHasher(
            password_salt=settings.auth.password_salt
        )
        if token_service is None:
            token_service = JWTTokenService(
                secret=settings.auth.jwt_secret,
                algorithm=settings.auth.jwt_algorithm,
                access_token_ttl=timedelta(minutes=settings.auth.access_token_ttl_minutes),
            )
        self.token_service = token_service
        self.refresh_token_ttl = refresh_token_ttl or timedelta(
            days=settings.auth.refresh_token_ttl_days
        )
        self.refresh_token_session_limit = (
            refresh_token_session_limit or settings.auth.refresh_token_session_limit
        )

    async def register(self, data: RegisterUser) -> AuthTokens:
        hashed_password = self.password_hasher.hash_password(data.password)

        async with self.uow() as uow:
            user = await uow.user.add_user(data, hashed_password)
            return await self._issue_tokens(uow, user)

    async def login(self, data: LoginUser) -> AuthTokens:
        async with self.uow() as uow:
            hashed_password = await uow.user.get_hashed_password_by_email(data.email)
            if hashed_password is None:
                raise app_exc.InvalidCredentials

            if not self.password_hasher.verify_password(data.password, hashed_password):
                raise app_exc.InvalidCredentials

            user = await uow.user.get_user_by_email(data.email)
            return await self._issue_tokens(uow, user)

    async def get_current_user(self, access_token: str) -> User:
        user_id = self.token_service.get_user_id_from_access_token(access_token)

        async with self.uow(read_only=True) as uow:
            return await uow.user.get_user(user_id)

    async def refresh(self, refresh_token: str) -> AuthTokens:
        token_hash = hash_refresh_token(refresh_token)
        now = datetime.now(UTC)

        async with self.uow() as uow:
            session = await uow.user.get_active_refresh_token(token_hash, now)
            if session is None:
                raise app_exc.InvalidToken

            await uow.user.revoke_refresh_token(token_hash)
            user = await uow.user.get_user(session.user_id)
            return await self._issue_tokens(uow, user)

    async def _issue_tokens(self, uow, user: User) -> AuthTokens:
        access_token = self.token_service.create_access_token(user.user_id)
        refresh_token = create_refresh_token()
        await uow.user.add_refresh_token(
            user.user_id,
            hash_refresh_token(refresh_token),
            datetime.now(UTC) + self.refresh_token_ttl,
        )
        await uow.user.revoke_oldest_active_refresh_tokens(
            user.user_id,
            self.refresh_token_session_limit,
            datetime.now(UTC),
        )
        return AuthTokens(access_token=access_token, refresh_token=refresh_token)
