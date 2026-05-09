from uuid import UUID
from typing import Any

from adapters.unitofwork import SQLAlchemyUnitOfWork
from domain.tags import normalize_tag_name
from domain.value_objects.audit import AuditEvent, AuditEntityType, AuditEventType
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

    async def get_tag_history(
        self,
        user_id: UUID,
        tag_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        async with self.uow(read_only=True) as uow:
            await self._check_if_tag_belongs_to_user(uow, user_id, tag_id)
            return await uow.audit.get_events(
                entity_type=AuditEntityType.TAG,
                entity_id=tag_id,
                limit=limit,
                offset=offset,
            )

    async def create_tag(self, user_id: UUID, name: str) -> Tag:
        async with self.uow() as uow:
            tag = await uow.tag.add_tag(user_id, name)
            await self._record_tag_event(
                uow,
                user_id=user_id,
                tag_id=tag.tag_id,
                event_type=AuditEventType.TAG_CREATED,
            )
            return tag

    async def ensure_tag(self, user_id: UUID, name: str) -> Tag:
        normalized_name = normalize_tag_name(name)

        async with self.uow() as uow:
            existing_tag = await uow.tag.find_tag_by_name(user_id, normalized_name)
            tag = await uow.tag.ensure_tag(user_id, normalized_name)

            if existing_tag is None:
                await self._record_tag_event(
                    uow,
                    user_id=user_id,
                    tag_id=tag.tag_id,
                    event_type=AuditEventType.TAG_CREATED,
                )

            return tag

    async def update_tag(self, user_id: UUID, tag_id: UUID, name: str) -> Tag:
        async with self.uow() as uow:
            await self._check_if_tag_exists(uow, user_id, tag_id)
            tag = await uow.tag.update_tag(user_id, tag_id, name)
            await self._record_tag_event(
                uow,
                user_id=user_id,
                tag_id=tag_id,
                event_type=AuditEventType.TAG_UPDATED,
                data={"changed_fields": ["name"]},
            )
            return tag

    async def delete_tag(self, user_id: UUID, tag_id: UUID) -> None:
        async with self.uow() as uow:
            await self._check_if_tag_exists(uow, user_id, tag_id)
            await uow.tag.delete_tag(user_id, tag_id)
            await self._record_tag_event(
                uow,
                user_id=user_id,
                tag_id=tag_id,
                event_type=AuditEventType.TAG_DELETED,
            )

    async def _check_if_tag_exists(self, uow, user_id: UUID, tag_id: UUID) -> None:
        if not await uow.tag.exists_tag(user_id, tag_id):
            raise app_exc.TagNotFound

    async def _check_if_tag_belongs_to_user(self, uow, user_id: UUID, tag_id: UUID) -> None:
        if not await uow.tag.exists_tag_including_deleted(user_id, tag_id):
            raise app_exc.TagNotFound

    @staticmethod
    async def _record_tag_event(
        uow,
        *,
        user_id: UUID,
        tag_id: UUID,
        event_type: AuditEventType,
        data: dict[str, Any] | None = None,
    ) -> None:
        await uow.audit.add_event(
            actor_user_id=user_id,
            entity_type=AuditEntityType.TAG,
            entity_id=tag_id,
            event_type=event_type,
            data=data,
        )
