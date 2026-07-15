from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import exceptions as app_exc
from services.auth import AuthService
from services.tags import TagService
from services.tasks import TaskService
from services.users import UserService
from dto.tasks import AddTask, TaskList, UpdateTaskData
from dto.users import UpdateUserData
from domain.value_objects.tags import Tag
from domain.value_objects.tasks import Task, TaskStatus
from domain.value_objects.users import AuthTokens, User
from presentation.app import create_app
from presentation.dependencies import (
    get_auth_service,
    get_current_user,
    get_tag_service,
    get_task_service,
    get_user_service,
)
from presentation.middlewares import RequestContextMiddleware, RequestLoggingMiddleware


class SuccessfulAuthService:
    async def register(self, data) -> AuthTokens:
        return AuthTokens(access_token="access-token", refresh_token="refresh-token")

    async def login(self, data) -> AuthTokens:
        return AuthTokens(access_token="access-token", refresh_token="refresh-token")

    async def refresh(self, refresh_token: str) -> AuthTokens:
        return AuthTokens(access_token="new-access-token", refresh_token="new-refresh-token")

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        return None

    async def get_current_user(self, access_token: str) -> User:
        raise NotImplementedError


class InvalidCredentialsAuthService(SuccessfulAuthService):
    async def login(self, data) -> AuthTokens:
        raise app_exc.InvalidCredentials


class AuthenticatedAuthService(SuccessfulAuthService):
    def __init__(self, user: User) -> None:
        self._user = user

    async def get_current_user(self, access_token: str) -> User:
        return self._user


class UpdatingUserService:
    async def update_user(self, user_id, data: UpdateUserData) -> User:
        return User(
            user_id=user_id,
            first_name=data.first_name or "First",
            last_name=data.last_name or "Last",
            email=data.email or "user@example.com",
            middle_name=data.middle_name,
        )


class TaskWorkflowService:
    def __init__(self) -> None:
        self.tasks: dict[UUID, Task] = {}

    async def create_task(self, user_id: UUID, data: AddTask) -> Task:
        task = Task(
            task_id=uuid4(),
            title=data.title,
            description=data.description,
            status=data.status,
            priority=data.priority,
            due_at=data.due_at,
            created_at=datetime(2026, 7, 12, 12),
            schedule=data.schedule,
        )
        self.tasks[task.task_id] = task
        return task

    async def get_tasks(self, user_id: UUID, filters) -> TaskList:
        return TaskList(tasks=list(self.tasks.values()), conflicts=[])

    async def update_task(self, user_id: UUID, task_id: UUID, data: UpdateTaskData) -> Task:
        task = self.tasks[task_id]
        updated = replace(
            task,
            title=data.title if data.title is not None else task.title,
            description=data.description if data.description is not None else task.description,
            status=data.status if data.status is not None else task.status,
            priority=data.priority if data.priority is not None else task.priority,
            due_at=data.due_at if data.due_at is not None else task.due_at,
            schedule=data.schedule if data.schedule is not None else task.schedule,
        )
        self.tasks[task_id] = updated
        return updated

    async def complete_task(self, user_id: UUID, task_id: UUID) -> Task:
        completed = replace(self.tasks[task_id], status=TaskStatus.COMPLETED)
        self.tasks[task_id] = completed
        return completed

    async def delete_task(self, user_id: UUID, task_id: UUID) -> None:
        del self.tasks[task_id]


class TagWorkflowService:
    def __init__(self) -> None:
        self.tags: dict[UUID, Tag] = {}

    async def create_tag(self, user_id: UUID, name: str) -> Tag:
        tag = Tag(tag_id=uuid4(), name=name, created_at=datetime(2026, 7, 12, 12))
        self.tags[tag.tag_id] = tag
        return tag

    async def get_tags(self, user_id: UUID, limit: int, offset: int) -> list[Tag]:
        return list(self.tags.values())[offset : offset + limit]

    async def update_tag(self, user_id: UUID, tag_id: UUID, name: str) -> Tag:
        updated = replace(self.tags[tag_id], name=name)
        self.tags[tag_id] = updated
        return updated

    async def delete_tag(self, user_id: UUID, tag_id: UUID) -> None:
        del self.tags[tag_id]


class ConflictingTagService(TagWorkflowService):
    async def create_tag(self, user_id: UUID, name: str) -> Tag:
        raise app_exc.TagAlreadyExists


@pytest.mark.asyncio
async def test_registration_returns_authentication_tokens() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "password": "correct-password",
                "first_name": "First",
                "last_name": "Last",
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "token_type": "bearer",
    }
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session_without_response_content() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "refresh-token"},
        )

    assert response.status_code == 204
    assert response.content == b""
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_invalid_credentials_return_safe_unauthorized_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(
        AuthService, InvalidCredentialsAuthService()
    )

    with caplog.at_level("INFO"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "user@example.com", "password": "wrong-password"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "wrong-password" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    completion_record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "http_request_completed"
    )
    assert getattr(completion_record, "error_code", None) == "invalid_credentials"
    assert getattr(completion_record, "client_ip", None) == "127.0.0.1"


@pytest.mark.asyncio
async def test_request_validation_does_not_echo_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    password = " leaked-password "
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())

    with caplog.at_level("INFO"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "user@example.com",
                    "password": password,
                    "first_name": "First",
                    "last_name": "Last",
                },
            )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"
    assert password not in response.text
    password_detail = next(
        detail for detail in response.json()["details"] if detail["location"][-1] == "password"
    )
    assert password_detail["code"] == "invalid_value"
    assert "Value error," not in password_detail["message"]
    completion_record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "http_request_completed"
    )
    response_details = response.json()["details"]
    assert getattr(completion_record, "validation_error_count", None) == len(response_details)
    assert getattr(completion_record, "validation_errors", None) == tuple(
        {
            "location": ".".join(str(part) for part in detail["location"]),
            "code": detail["code"],
        }
        for detail in response_details
    )
    assert getattr(completion_record, "validation_errors_truncated", None) is False
    assert password not in str(getattr(completion_record, "validation_errors", None))


@pytest.mark.asyncio
async def test_current_user_endpoint_returns_authenticated_user() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user.user_id),
        "first_name": "First",
        "last_name": "Last",
        "email": "user@example.com",
        "middle_name": None,
    }


@pytest.mark.asyncio
async def test_current_user_endpoint_requires_bearer_token() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_authenticated_request_log_contains_verified_user_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(
        AuthService, AuthenticatedAuthService(user)
    )

    with caplog.at_level("INFO"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": "Bearer valid-access-token"},
            )

    assert response.status_code == 200
    completion_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "http_request_completed"
    ]
    assert len(completion_records) == 1
    assert getattr(completion_records[0], "user_id", None) == str(user.user_id)
    assert not hasattr(completion_records[0], "client_ip")


@pytest.mark.asyncio
async def test_request_log_identifies_routed_resource(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()

    @app.get("/tasks/{task_id}", name="get_task")
    async def get_task(task_id: UUID) -> dict[str, str]:
        return {"task_id": str(task_id)}

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
    task_id = uuid4()

    with caplog.at_level("INFO"):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/tasks/{task_id}")

    assert response.status_code == 200
    completion_record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "http_request_completed"
    )
    assert getattr(completion_record, "path", None) == "/tasks/{task_id}"
    assert getattr(completion_record, "operation", None) == "get_task"
    assert getattr(completion_record, "path_params", None) == {"task_id": str(task_id)}


@pytest.mark.asyncio
async def test_authenticated_user_can_update_profile() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_user_service] = lambda: cast(UserService, UpdatingUserService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"first_name": "Updated", "email": "updated@example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user.user_id),
        "first_name": "Updated",
        "last_name": "Last",
        "email": "updated@example.com",
        "middle_name": None,
    }


@pytest.mark.asyncio
async def test_user_can_manage_a_task_through_http() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )
    task_service = TaskWorkflowService()

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_task_service] = lambda: cast(TaskService, task_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/tasks",
            json={
                "title": "Prepare presentation",
                "due_at": "2026-07-13T18:00:00",
                "schedule": {
                    "starts_at": "2026-07-13T16:00:00",
                    "ends_at": "2026-07-13T17:00:00",
                },
            },
        )
        task_id = created.json()["task_id"]
        updated = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"priority": "high"},
        )
        completed = await client.post(f"/api/v1/tasks/{task_id}/complete")
        listed = await client.get("/api/v1/tasks", params={"statuses": "completed"})
        deleted = await client.delete(f"/api/v1/tasks/{task_id}")
        listed_after_delete = await client.get("/api/v1/tasks")

    assert created.status_code == 201
    assert created.json()["title"] == "Prepare presentation"
    assert created.json()["schedule"] == {
        "starts_at": "2026-07-13T16:00:00",
        "ends_at": "2026-07-13T17:00:00",
    }
    assert updated.status_code == 200
    assert updated.json()["priority"] == "high"
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert [task["task_id"] for task in listed.json()["tasks"]] == [task_id]
    assert listed.json()["conflicts"] == []
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert listed_after_delete.json()["tasks"] == []


@pytest.mark.asyncio
async def test_task_datetime_with_timezone_is_rejected() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_task_service] = lambda: cast(TaskService, TaskWorkflowService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/tasks",
            json={
                "title": "Prepare presentation",
                "due_at": "2026-07-13T18:00:00+03:00",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"
    due_at_detail = next(
        detail for detail in response.json()["details"] if detail["location"][-1] == "due_at"
    )
    assert due_at_detail["code"] == "timezone_not_allowed"


@pytest.mark.asyncio
async def test_user_can_manage_tags_through_http() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )
    tag_service = TagWorkflowService()

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_tag_service] = lambda: cast(TagService, tag_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post("/api/v1/tags", json={"name": "  Work  "})
        tag_id = created.json()["tag_id"]
        updated = await client.patch(
            f"/api/v1/tags/{tag_id}",
            json={"name": "Important"},
        )
        listed = await client.get("/api/v1/tags")
        deleted = await client.delete(f"/api/v1/tags/{tag_id}")
        listed_after_delete = await client.get("/api/v1/tags")

    assert created.status_code == 201
    assert created.json()["name"] == "Work"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Important"
    assert [tag["tag_id"] for tag in listed.json()["tags"]] == [tag_id]
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert listed_after_delete.json()["tags"] == []


@pytest.mark.asyncio
async def test_duplicate_tag_returns_conflict() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
    )

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_tag_service] = lambda: cast(TagService, ConflictingTagService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/tags", json={"name": "Work"})

    assert response.status_code == 409
    assert response.json()["code"] == "tag_already_exists"
