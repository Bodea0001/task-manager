from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from presentation.dependencies import CurrentUserDependency, TagServiceDependency
from presentation.schemas.audit import AuditEventListResponse
from presentation.schemas.tags import TagListResponse, TagNameRequest, TagResponse


router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("", response_model=TagListResponse)
async def list_tags(
    current_user: CurrentUserDependency,
    tag_service: TagServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TagListResponse:
    tags = await tag_service.get_tags(current_user.user_id, limit, offset)
    return TagListResponse.from_domain(tags)


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    request: TagNameRequest,
    current_user: CurrentUserDependency,
    tag_service: TagServiceDependency,
) -> TagResponse:
    tag = await tag_service.create_tag(current_user.user_id, request.name)
    return TagResponse.from_domain(tag)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: UUID,
    current_user: CurrentUserDependency,
    tag_service: TagServiceDependency,
) -> TagResponse:
    tag = await tag_service.get_tag(current_user.user_id, tag_id)
    return TagResponse.from_domain(tag)


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID,
    request: TagNameRequest,
    current_user: CurrentUserDependency,
    tag_service: TagServiceDependency,
) -> TagResponse:
    tag = await tag_service.update_tag(current_user.user_id, tag_id, request.name)
    return TagResponse.from_domain(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    current_user: CurrentUserDependency,
    tag_service: TagServiceDependency,
) -> Response:
    await tag_service.delete_tag(current_user.user_id, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{tag_id}/history", response_model=AuditEventListResponse)
async def get_tag_history(
    tag_id: UUID,
    current_user: CurrentUserDependency,
    tag_service: TagServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListResponse:
    events = await tag_service.get_tag_history(current_user.user_id, tag_id, limit, offset)
    return AuditEventListResponse.from_domain(events)
