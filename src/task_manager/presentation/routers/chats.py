from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from presentation.dependencies import (
    AgentApplicationDependency,
    ChatServiceDependency,
    CurrentUserDependency,
)
from presentation.schemas.chats import (
    ChatListQuery,
    ChatListResponse,
    ChatMessageListQuery,
    ChatMessageListResponse,
    ChatResponse,
    CreateChatRequest,
    UpdateChatRequest,
)


router = APIRouter(prefix="/chats", tags=["Chats"])


@router.get("", response_model=ChatListResponse)
async def list_chats(
    filters: Annotated[ChatListQuery, Query()],
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatListResponse:
    page = await chat_service.get_chats(current_user.user_id, filters.to_dto())
    return ChatListResponse.from_domain(page)


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    request: CreateChatRequest,
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatResponse:
    chat = await chat_service.create_chat(current_user.user_id, request.to_dto())
    return ChatResponse.from_domain(chat)


@router.get("/active", response_model=ChatResponse)
async def get_active_chat(
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatResponse:
    chat = await chat_service.get_active_chat(current_user.user_id)
    return ChatResponse.from_domain(chat)


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: UUID,
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatResponse:
    chat = await chat_service.get_chat(current_user.user_id, chat_id)
    return ChatResponse.from_domain(chat)


@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: UUID,
    request: UpdateChatRequest,
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatResponse:
    chat = await chat_service.update_chat(current_user.user_id, chat_id, request.to_dto())
    return ChatResponse.from_domain(chat)


@router.post("/{chat_id}/activate", response_model=ChatResponse)
async def activate_chat(
    chat_id: UUID,
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatResponse:
    chat = await chat_service.activate_chat(current_user.user_id, chat_id)
    return ChatResponse.from_domain(chat)


@router.get("/{chat_id}/messages", response_model=ChatMessageListResponse)
async def list_chat_messages(
    chat_id: UUID,
    filters: Annotated[ChatMessageListQuery, Query()],
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
) -> ChatMessageListResponse:
    page = await chat_service.get_chat_messages(
        current_user.user_id,
        chat_id,
        filters.to_dto(),
    )
    return ChatMessageListResponse.from_domain(page)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID,
    current_user: CurrentUserDependency,
    chat_service: ChatServiceDependency,
    agent: AgentApplicationDependency,
) -> Response:
    await chat_service.check_user_can_use_chat(current_user.user_id, chat_id)
    await agent.reset_chat_checkpoint(chat_id)
    await chat_service.delete_chat(current_user.user_id, chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
