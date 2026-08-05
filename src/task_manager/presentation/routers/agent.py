from collections.abc import AsyncIterable
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from presentation.agent_stream import AGENT_STREAM_MEDIA_TYPE
from presentation.dependencies import (
    AgentStreamCoordinatorDependency,
    CurrentUserDependency,
    RequestIdDependency,
)
from presentation.schemas.agent import AgentRequest


router = APIRouter(prefix="/chats", tags=["Assistant"])


@router.post(
    "/{chat_id}/agent",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Agent plan progress and final result event stream.",
            "content": {AGENT_STREAM_MEDIA_TYPE: {}},
        }
    },
)
async def run_agent(
    chat_id: UUID,
    agent_request: AgentRequest,
    current_user: CurrentUserDependency,
    coordinator: AgentStreamCoordinatorDependency,
    request_id: RequestIdDependency,
) -> StreamingResponse:
    """Run an assistant request and stream UI-safe progress events."""
    stream = await coordinator.start(
        message=agent_request.message,
        user_id=current_user.user_id,
        chat_id=chat_id,
        request_id=request_id,
    )
    return _streaming_response(stream.events())


@router.post(
    "/{chat_id}/agent/retry",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Retried agent plan progress and final result event stream.",
            "content": {AGENT_STREAM_MEDIA_TYPE: {}},
        }
    },
)
async def retry_agent(
    chat_id: UUID,
    current_user: CurrentUserDependency,
    coordinator: AgentStreamCoordinatorDependency,
    request_id: RequestIdDependency,
) -> StreamingResponse:
    """Retry the latest unresolved request without accepting duplicate message text."""
    stream = await coordinator.retry(
        user_id=current_user.user_id,
        chat_id=chat_id,
        request_id=request_id,
    )
    return _streaming_response(stream.events())


def _streaming_response(events: AsyncIterable[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type=AGENT_STREAM_MEDIA_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
