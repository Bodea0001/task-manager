from uuid import UUID

from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.tags import normalize_tag_name
from domain.value_objects.tags import Tag
import exceptions as app_exc


class TagService:
    """Application service with tag operations intended for agent tools/use cases."""

    def __init__(self, uow: SQLAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def get_tags(self, limit: int | None = None, offset: int | None = None) -> list[Tag]:
        async with self.uow(read_only=True) as uow:
            return await uow.tag.get_tags(limit=limit, offset=offset)

    async def get_tag(self, tag_id: UUID) -> Tag:
        async with self.uow(read_only=True) as uow:
            await self._check_if_tag_exists(uow, tag_id)
            return await uow.tag.get_tag(tag_id)

    async def create_tag(self, name: str) -> Tag:
        async with self.uow() as uow:
            return await uow.tag.add_tag(name)

    async def ensure_tag(self, name: str) -> Tag:
        async with self.uow() as uow:
            return await uow.tag.ensure_tag(normalize_tag_name(name))

    async def update_tag(self, tag_id: UUID, name: str) -> Tag:
        async with self.uow() as uow:
            await self._check_if_tag_exists(uow, tag_id)
            return await uow.tag.update_tag(tag_id, name)

    async def delete_tag(self, tag_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_tag_exists(uow, tag_id)
            await uow.tag.delete_tag(tag_id)

    async def _check_if_tag_exists(self, uow, tag_id: UUID) -> None:
        if not await uow.tag.exists_tag(tag_id):
            raise app_exc.TagNotFound
