from typing import Annotated
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, StringConstraints

from domain.value_objects.tags import Tag


TagName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TagNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TagName


class TagResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tag_id: UUID
    name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, tag: Tag) -> "TagResponse":
        return cls(tag_id=tag.tag_id, name=tag.name, created_at=tag.created_at)


class TagListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tags: tuple[TagResponse, ...]

    @classmethod
    def from_domain(cls, tags: list[Tag]) -> "TagListResponse":
        return cls(tags=tuple(TagResponse.from_domain(tag) for tag in tags))
