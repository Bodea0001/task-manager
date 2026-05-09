from uuid import UUID

from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.tags import normalize_tag_name
from domain.value_objects.tags import Tag
import exceptions as app_exc


class TagService:
    """Application service with tag operations intended for agent tools/use cases."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def get_tags(
        self,
        user_id: UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Tag]:
        async with self.uow(read_only=True) as uow:
            return await uow.tag.get_tags(user_id, limit=limit, offset=offset)

    async def get_tag(self, user_id: UUID, tag_id: UUID) -> Tag:
        async with self.uow(read_only=True) as uow:
            await self._check_if_tag_exists(uow, user_id, tag_id)
            return await uow.tag.get_tag(user_id, tag_id)

    async def create_tag(self, user_id: UUID, name: str) -> Tag:
        async with self.uow() as uow:
            return await uow.tag.add_tag(user_id, name)

    async def ensure_tag(self, user_id: UUID, name: str) -> Tag:
        async with self.uow() as uow:
            return await uow.tag.ensure_tag(user_id, normalize_tag_name(name))

    async def update_tag(self, user_id: UUID, tag_id: UUID, name: str) -> Tag:
        async with self.uow() as uow:
            await self._check_if_tag_exists(uow, user_id, tag_id)
            return await uow.tag.update_tag(user_id, tag_id, name)

    async def delete_tag(self, user_id: UUID, tag_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_tag_exists(uow, user_id, tag_id)
            await uow.tag.delete_tag(user_id, tag_id)

    async def _check_if_tag_exists(self, uow, user_id: UUID, tag_id: UUID) -> None:
        if not await uow.tag.exists_tag(user_id, tag_id):
            raise app_exc.TagNotFound
