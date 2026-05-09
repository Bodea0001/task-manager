from uuid import UUID
from typing import Concatenate, ParamSpec, TypeVar
from collections.abc import Awaitable, Callable
from functools import wraps

from sqlalchemy import select, insert, update, delete
from sqlalchemy.exc import NoResultFound
from sqlalchemy.dialects.postgresql import insert as pg_insert

import exceptions as app_exc
from models.tags import Tag as TagModel
from domain.value_objects.tags import Tag
from adapters.repository import SQLAlchemyRepository


P = ParamSpec("P")
R = TypeVar("R")


def translate_repository_errors(
    method: Callable[Concatenate["TagRepository", P], Awaitable[R]],
) -> Callable[Concatenate["TagRepository", P], Awaitable[R]]:
    @wraps(method)
    async def wrapper(self: "TagRepository", /, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await method(self, *args, **kwargs)
        except NoResultFound:
            raise app_exc.TagNotFound

    return wrapper


class TagRepository(SQLAlchemyRepository):
    async def get_tags(
        self,
        user_id: UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Tag]:
        stmt = (
            select(TagModel)
            .where(TagModel.creator_id == user_id, self._tag_is_not_deleted())
            .order_by(TagModel.name)
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return [self._model_to_tag(model) for model in result.scalars().all()]

    @translate_repository_errors
    async def get_tag(self, user_id: UUID, tag_id: UUID) -> Tag:
        stmt = select(TagModel).where(
            TagModel.creator_id == user_id,
            TagModel.tag_id == tag_id,
            self._tag_is_not_deleted(),
        )

        result = await self.session.execute(stmt)
        return self._model_to_tag(result.scalar_one())

    async def exists_tag(self, user_id: UUID, tag_id: UUID) -> bool:
        stmt = select(
            select(1)
            .select_from(TagModel)
            .where(
                TagModel.creator_id == user_id,
                TagModel.tag_id == tag_id,
                self._tag_is_not_deleted(),
            )
            .exists()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def ensure_tag(self, user_id: UUID, name: str) -> Tag:
        stmt = (
            pg_insert(TagModel)
            .values(creator_id=user_id, name=name)
            .on_conflict_do_nothing(
                index_elements=["creator_id", "name"],
                index_where=self._tag_is_not_deleted(),
            )
            .returning(TagModel)
        )

        result = await self.session.execute(stmt)
        tag_model = result.scalar_one_or_none()

        if tag_model is None:
            return await self.get_tag_by_name(user_id, name)

        return self._model_to_tag(tag_model)

    async def add_tag(self, user_id: UUID, name: str) -> Tag:
        stmt = insert(TagModel).values(creator_id=user_id, name=name).returning(TagModel)

        result = await self.session.execute(stmt)
        return self._model_to_tag(result.scalar_one())

    @translate_repository_errors
    async def get_tag_by_name(self, user_id: UUID, name: str) -> Tag:
        stmt = select(TagModel).where(
            TagModel.creator_id == user_id,
            TagModel.name == name,
            self._tag_is_not_deleted(),
        )

        result = await self.session.execute(stmt)
        return self._model_to_tag(result.scalar_one())

    @translate_repository_errors
    async def update_tag(self, user_id: UUID, tag_id: UUID, name: str) -> Tag:
        stmt = (
            update(TagModel)
            .values(name=name)
            .where(
                TagModel.creator_id == user_id,
                TagModel.tag_id == tag_id,
                self._tag_is_not_deleted(),
            )
            .returning(TagModel)
        )

        result = await self.session.execute(stmt)
        return self._model_to_tag(result.scalar_one())

    async def delete_tag(self, user_id: UUID, tag_id: UUID) -> None:
        stmt = delete(TagModel).where(
            TagModel.creator_id == user_id,
            TagModel.tag_id == tag_id,
            self._tag_is_not_deleted(),
        )

        await self.session.execute(stmt)

    @staticmethod
    def _tag_is_not_deleted():
        return TagModel.deleted_at.is_(None)

    @staticmethod
    def _model_to_tag(model: TagModel) -> Tag:
        return Tag(
            tag_id=model.tag_id,
            name=model.name,
            created_at=model.created_at,
        )
