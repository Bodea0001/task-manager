from uuid import UUID

from sqlalchemy import select, insert, update, delete
from sqlalchemy.exc import NoResultFound
from sqlalchemy.dialects.postgresql import insert as pg_insert

import exceptions as app_exc
from models.tags import Tag as TagModel
from domain.value_objects.tags import Tag
from adapters.repository import SQLAlchemyRepository


class TagRepository(SQLAlchemyRepository):
    async def get_tags(self, limit: int | None = None, offset: int | None = None) -> list[Tag]:
        stmt = select(TagModel).order_by(TagModel.name).limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return [self._model_to_tag(model) for model in result.scalars().all()]

    async def get_tag(self, tag_id: UUID) -> Tag:
        stmt = select(TagModel).where(TagModel.tag_id == tag_id)

        try:
            result = await self.session.execute(stmt)
            return self._model_to_tag(result.scalar_one())
        except NoResultFound:
            raise app_exc.TagNotFound

    async def exists_tag(self, tag_id: UUID) -> bool:
        stmt = select(select(1).select_from(TagModel).where(TagModel.tag_id == tag_id).exists())
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def ensure_tag(self, name: str) -> Tag:
        stmt = (
            pg_insert(TagModel)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=["name"])
            .returning(TagModel)
        )

        result = await self.session.execute(stmt)
        tag_model = result.scalar_one_or_none()

        if tag_model is None:
            return await self.get_tag_by_name(name)

        return self._model_to_tag(tag_model)

    async def add_tag(self, name: str) -> Tag:
        stmt = insert(TagModel).values(name=name).returning(TagModel)

        result = await self.session.execute(stmt)
        return self._model_to_tag(result.scalar_one())

    async def get_tag_by_name(self, name: str) -> Tag:
        stmt = select(TagModel).where(TagModel.name == name)

        try:
            result = await self.session.execute(stmt)
            return self._model_to_tag(result.scalar_one())
        except NoResultFound:
            raise app_exc.TagNotFound

    async def update_tag(self, tag_id: UUID, name: str) -> Tag:
        stmt = (
            update(TagModel).values(name=name).where(TagModel.tag_id == tag_id).returning(TagModel)
        )

        try:
            result = await self.session.execute(stmt)
            return self._model_to_tag(result.scalar_one())
        except NoResultFound:
            raise app_exc.TagNotFound

    async def delete_tag(self, tag_id: UUID) -> None:
        stmt = delete(TagModel).where(TagModel.tag_id == tag_id)

        await self.session.execute(stmt)

    @staticmethod
    def _model_to_tag(model: TagModel) -> Tag:
        return Tag(
            tag_id=model.tag_id,
            name=model.name,
            created_at=model.created_at,
        )
