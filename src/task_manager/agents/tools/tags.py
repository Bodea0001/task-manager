from uuid import UUID
from typing import Any

from langchain.tools import tool

import exceptions as app_exc
from agents.tools.registry import ToolProfile, register_tool
from agents.schemas.tools import (
    HiddenRuntime,
    CreateTagInput,
    EnsureTagInput,
    GetTagInput,
    GetTagHistoryInput,
    ListTagsInput,
    UpdateTagInput,
)
from domain.value_objects.audit import AuditEvent
from domain.value_objects.tags import Tag


@register_tool(read_only=True, profiles=(ToolProfile.TASK_WRITE,))
@tool(
    "list_tags",
    description="List the authenticated user's tags.",
    args_schema=ListTagsInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def list_tags(
    runtime: HiddenRuntime,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List tags.

    Args:
        limit: Maximum tags to return.
        offset: Tags to skip.
    """
    tags = await runtime.context.tag_service.get_tags(
        runtime.context.user_id,
        limit=limit,
        offset=offset,
    )
    return {"status": "ok", "count": len(tags), "tags": [_tag_to_dict(tag) for tag in tags]}


@register_tool(read_only=True, profiles=(ToolProfile.TAGS,))
@tool(
    "get_tag",
    description="Get one tag by exact tag id.",
    args_schema=GetTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_tag(tag_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Get one tag.

    Args:
        tag_id: Exact tag id.
    """
    try:
        tag = await runtime.context.tag_service.get_tag(runtime.context.user_id, tag_id)
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)

    return {"status": "ok", "tag": _tag_to_dict(tag)}


@register_tool(read_only=True, profiles=(ToolProfile.TAGS,))
@tool(
    "get_tag_history",
    description="Get audit history for one tag by exact tag id.",
    args_schema=GetTagHistoryInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_tag_history(
    tag_id: UUID,
    runtime: HiddenRuntime,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Get tag audit history.

    Args:
        tag_id: Exact tag id.
        limit: Maximum history events to return.
        offset: History events to skip.
    """
    try:
        events = await runtime.context.tag_service.get_tag_history(
            runtime.context.user_id,
            tag_id,
            limit=limit,
            offset=offset,
        )
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)

    return {"status": "ok", "events": [_audit_event_to_dict(event) for event in events]}


@register_tool(read_only=False, profiles=(ToolProfile.TAGS,))
@tool(
    "create_tag",
    description="Create one tag for the authenticated user.",
    args_schema=CreateTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def create_tag(name: str, runtime: HiddenRuntime) -> dict[str, Any]:
    """Create one tag.

    Args:
        name: Tag name.
    """
    try:
        tag = await runtime.context.tag_service.create_tag(runtime.context.user_id, name)
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    return {"status": "ok", "tag": _tag_to_dict(tag)}


@register_tool(read_only=False, profiles=(ToolProfile.TASK_WRITE,))
@tool(
    "ensure_tag",
    description="Find or create one tag by name for the authenticated user.",
    args_schema=EnsureTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def ensure_tag(name: str, runtime: HiddenRuntime) -> dict[str, Any]:
    """Find or create one tag.

    Args:
        name: Tag name.
    """
    try:
        tag = await runtime.context.tag_service.ensure_tag(runtime.context.user_id, name)
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    return {"status": "ok", "tag": _tag_to_dict(tag)}


@register_tool(read_only=False, profiles=(ToolProfile.TAGS,))
@tool(
    "update_tag",
    description="Rename one tag by exact tag id.",
    args_schema=UpdateTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def update_tag(tag_id: UUID, name: str, runtime: HiddenRuntime) -> dict[str, Any]:
    """Rename one tag.

    Args:
        tag_id: Exact tag id.
        name: New tag name.
    """
    try:
        tag = await runtime.context.tag_service.update_tag(runtime.context.user_id, tag_id, name)
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)

    return {"status": "ok", "tag": _tag_to_dict(tag)}


def _tool_error(status: str, message: str, *, retryable: bool) -> dict[str, Any]:
    return {"status": status, "message": message, "retryable": retryable}


def _tag_to_dict(tag: Tag) -> dict[str, Any]:
    return {
        "tag_id": str(tag.tag_id),
        "name": tag.name,
        "created_at": tag.created_at.isoformat(),
    }


def _audit_event_to_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "actor_user_id": str(event.actor_user_id),
        "entity_type": event.entity_type.value,
        "entity_id": str(event.entity_id),
        "event_type": event.event_type.value,
        "occurred_at": event.occurred_at.isoformat(),
        "data": event.data,
    }
