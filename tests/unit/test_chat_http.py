from datetime import datetime
from dataclasses import replace
from uuid import UUID, uuid4
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

import exceptions as app_exc
from agents.app import AgentApplication
from services.chats import ChatService
from dto.chats import CreateChatData, ListChatMessages, ListChats, UpdateChatData
from domain.value_objects.chats import (
    Chat,
    ChatMessage,
    ChatMessagePage,
    ChatMessageRole,
    ChatPage,
)
from domain.value_objects.users import User
from presentation.app import create_app
from presentation.dependencies import (
    get_agent_application,
    get_chat_service,
    get_current_user,
)


class ChatWorkflowService:
    def __init__(self) -> None:
        self.chats: dict[UUID, Chat] = {}
        self.messages: dict[UUID, list[ChatMessage]] = {}
        self._created_count = 0

    async def create_chat(self, user_id: UUID, data: CreateChatData) -> Chat:
        self.chats = {
            chat_id: replace(chat, is_active=False) for chat_id, chat in self.chats.items()
        }
        self._created_count += 1
        chat = Chat(
            chat_id=uuid4(),
            creator_id=user_id,
            title=data.title,
            is_active=True,
            created_at=datetime(2026, 7, 13, 12, self._created_count),
        )
        self.chats[chat.chat_id] = chat
        self.messages[chat.chat_id] = []
        return chat

    async def get_chats(self, user_id: UUID, filters: ListChats) -> ChatPage:
        chats = sorted(
            (chat for chat in self.chats.values() if chat.creator_id == user_id),
            key=lambda chat: chat.created_at,
            reverse=True,
        )
        selected = chats[filters.offset : filters.offset + filters.limit + 1]
        next_offset = filters.offset + filters.limit if len(selected) > filters.limit else None
        return ChatPage(tuple(selected[: filters.limit]), next_offset)

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        await self.check_user_can_use_chat(user_id, chat_id)
        return self.chats[chat_id]

    async def get_active_chat(self, user_id: UUID) -> Chat:
        for chat in self.chats.values():
            if chat.creator_id == user_id and chat.is_active:
                return chat
        raise app_exc.ChatNotFound

    async def update_chat(
        self,
        user_id: UUID,
        chat_id: UUID,
        data: UpdateChatData,
    ) -> Chat:
        chat = await self.get_chat(user_id, chat_id)
        updated = replace(chat, title=data.title)
        self.chats[chat_id] = updated
        return updated

    async def activate_chat(self, user_id: UUID, chat_id: UUID) -> Chat:
        await self.check_user_can_use_chat(user_id, chat_id)
        self.chats = {
            item_id: replace(chat, is_active=item_id == chat_id)
            for item_id, chat in self.chats.items()
        }
        return self.chats[chat_id]

    async def get_chat_messages(
        self,
        user_id: UUID,
        chat_id: UUID,
        filters: ListChatMessages,
    ) -> ChatMessagePage:
        await self.check_user_can_use_chat(user_id, chat_id)
        messages = self.messages[chat_id]
        page_end = len(messages) - filters.offset
        page_start = max(0, page_end - filters.limit)
        next_offset = filters.offset + filters.limit if page_start > 0 else None
        return ChatMessagePage(tuple(messages[page_start:page_end]), next_offset)

    async def check_user_can_use_chat(self, user_id: UUID, chat_id: UUID) -> None:
        chat = self.chats.get(chat_id)
        if chat is None or chat.creator_id != user_id:
            raise app_exc.ChatNotFound

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> None:
        await self.check_user_can_use_chat(user_id, chat_id)
        del self.chats[chat_id]
        del self.messages[chat_id]


class CheckpointWorkflow:
    def __init__(self) -> None:
        self.reset_chat_ids: set[UUID] = set()

    async def reset_chat_checkpoint(self, chat_id: UUID) -> None:
        self.reset_chat_ids.add(chat_id)


def _authenticated_user() -> User:
    return User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
    )


def _create_chat_app(
    chat_service: ChatWorkflowService,
    checkpoint: CheckpointWorkflow,
):
    user = _authenticated_user()

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_chat_service] = lambda: cast(ChatService, chat_service)
    app.dependency_overrides[get_agent_application] = lambda: cast(
        AgentApplication,
        checkpoint,
    )
    return app


@pytest.mark.asyncio
async def test_user_can_manage_chat_history_through_http() -> None:
    chat_service = ChatWorkflowService()
    checkpoint = CheckpointWorkflow()
    app = _create_chat_app(chat_service, checkpoint)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post("/api/v1/chats", json={"title": "Planning"})
        second = await client.post("/api/v1/chats", json={})
        first_chat_id = UUID(first.json()["chat_id"])
        second_chat_id = UUID(second.json()["chat_id"])
        chat_service.messages[first_chat_id] = [
            ChatMessage(
                message_id=uuid4(),
                chat_id=first_chat_id,
                role=ChatMessageRole.USER,
                content="What is due today?",
                created_at=datetime(2026, 7, 13, 12, 10),
            ),
            ChatMessage(
                message_id=uuid4(),
                chat_id=first_chat_id,
                role=ChatMessageRole.ASSISTANT,
                content="One task is due today.",
                created_at=datetime(2026, 7, 13, 12, 11),
            ),
        ]

        listed = await client.get("/api/v1/chats", params={"limit": 1})
        active = await client.get("/api/v1/chats/active")
        renamed = await client.patch(
            f"/api/v1/chats/{first_chat_id}",
            json={"title": "Daily planning"},
        )
        activated = await client.post(f"/api/v1/chats/{first_chat_id}/activate")
        newest_messages = await client.get(
            f"/api/v1/chats/{first_chat_id}/messages",
            params={"limit": 1},
        )
        older_messages = await client.get(
            f"/api/v1/chats/{first_chat_id}/messages",
            params={"limit": 1, "offset": 1},
        )
        deleted = await client.delete(f"/api/v1/chats/{first_chat_id}")
        missing = await client.get(f"/api/v1/chats/{first_chat_id}")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["title"] == "New chat"
    assert [chat["chat_id"] for chat in listed.json()["chats"]] == [str(second_chat_id)]
    assert listed.json()["next_offset"] == 1
    assert active.json()["chat_id"] == str(second_chat_id)
    assert renamed.json()["title"] == "Daily planning"
    assert activated.json()["is_active"] is True
    assert [message["role"] for message in newest_messages.json()["messages"]] == ["assistant"]
    assert newest_messages.json()["next_offset"] == 1
    assert [message["role"] for message in older_messages.json()["messages"]] == ["user"]
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["code"] == "chat_not_found"
    assert first_chat_id in checkpoint.reset_chat_ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path, payload, expected_status, expected_code",
    (
        (
            "POST",
            "/api/v1/chats",
            {"title": "   "},
            422,
            "request_validation_error",
        ),
        ("GET", "/api/v1/chats?limit=101", None, 422, "request_validation_error"),
        (
            "PATCH",
            f"/api/v1/chats/{uuid4()}",
            {"title": "Renamed"},
            404,
            "chat_not_found",
        ),
    ),
)
async def test_invalid_chat_request_is_rejected(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
    expected_code: str,
) -> None:
    app = _create_chat_app(ChatWorkflowService(), CheckpointWorkflow())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(method, path, json=payload)

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
