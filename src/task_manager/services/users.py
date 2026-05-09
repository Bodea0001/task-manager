from uuid import UUID

from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.value_objects.users import User
from dto.users import UpdateUserData


class UserService:
    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def get_user(self, user_id: UUID) -> User:
        async with self.uow(read_only=True) as uow:
            return await uow.user.get_user(user_id)

    async def update_user(self, user_id: UUID, data: UpdateUserData) -> User:
        async with self.uow() as uow:
            await uow.user.get_user(user_id)
            return await uow.user.update_user(user_id, data)
