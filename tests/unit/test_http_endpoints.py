from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import exceptions as app_exc
from config import HTTPConfig
from services.auth import AuthService
from services.agent_usage import AgentUsageService
from services.tags import TagService
from services.tasks import TaskService
from services.users import UserService
from dto.tasks import AddTask, TaskList, UpdateTaskData
from dto.users import UpdateUserData
from domain.value_objects.tags import Tag
from domain.value_objects.tasks import Task, TaskStatus
from domain.value_objects.users import AuthTokens, User
from domain.value_objects.agent_usage import AgentAccessLevel, AgentRunAllowance
from presentation.app import create_app
from presentation.auth_protection import RateLimitDecision, RegistrationPermit
from presentation.dependencies import (
    get_auth_service,
    get_anonymous_auth_protection,
    get_agent_usage_service,
    get_current_user,
    get_tag_service,
    get_task_service,
    get_user_service,
)
from presentation.middlewares import RequestContextMiddleware, RequestLoggingMiddleware


class SuccessfulAuthService:
    refresh_token_ttl = timedelta(days=30)

    def __init__(self) -> None:
        self.refreshed_tokens: list[str] = []
        self.revoked_tokens: list[str] = []
        self.register_calls = 0
        self.login_calls = 0

    async def register(self, data) -> AuthTokens:
        self.register_calls += 1
        return AuthTokens(access_token="access-token", refresh_token="refresh-token")

    async def login(self, data) -> AuthTokens:
        self.login_calls += 1
        return AuthTokens(access_token="access-token", refresh_token="refresh-token")

    async def refresh(self, refresh_token: str) -> AuthTokens:
        self.refreshed_tokens.append(refresh_token)
        return AuthTokens(access_token="new-access-token", refresh_token="new-refresh-token")

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        self.revoked_tokens.append(refresh_token)

    async def get_current_user(self, access_token: str) -> User:
        raise NotImplementedError


class InvalidCredentialsAuthService(SuccessfulAuthService):
    async def login(self, data) -> AuthTokens:
        self.login_calls += 1
        raise app_exc.InvalidCredentials


class AuthenticatedAuthService(SuccessfulAuthService):
    def __init__(self, user: User) -> None:
        super().__init__()
        self._user = user

    async def get_current_user(self, access_token: str) -> User:
        return self._user


class UpdatingUserService:
    async def update_user(self, user_id, data: UpdateUserData) -> User:
        return User(
            user_id=user_id,
            first_name=data.first_name or "First",
            last_name=data.last_name or "Last",
            email="user@example.com",
            email_verified=True,
            middle_name=data.middle_name,
        )


class AgentUsageWorkflow:
    allowance = AgentRunAllowance(
        user_id=UUID(int=0),
        used=2,
        access_level=AgentAccessLevel.LIMITED,
        limit=8,
        remaining=6,
    )

    async def get_allowance(self, user_id: UUID) -> AgentRunAllowance:
        return replace(self.allowance, user_id=user_id)


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


class RegistrationPermitWorkflow:
    def __init__(self) -> None:
        self.confirmed = False
        self.released = False

    async def confirm(self) -> None:
        self.confirmed = True

    async def release(self) -> None:
        self.released = True


class AuthProtectionWorkflow:
    def __init__(self) -> None:
        self.registration_decision = RateLimitDecision(allowed=True)
        self.login_decision = RateLimitDecision(allowed=True)
        self.registration_available = True
        self.client_addresses: list[str] = []
        self.permits: list[RegistrationPermitWorkflow] = []

    async def check_registration_attempt(self, client_address: str) -> RateLimitDecision:
        self.client_addresses.append(client_address)
        return self.registration_decision

    async def check_login_attempt(self, client_address: str) -> RateLimitDecision:
        self.client_addresses.append(client_address)
        return self.login_decision

    async def reserve_registration(self, client_address: str) -> RegistrationPermit | None:
        if not self.registration_available:
            return None
        permit = RegistrationPermitWorkflow()
        self.permits.append(permit)
        return permit


class UnavailableAuthProtectionWorkflow(AuthProtectionWorkflow):
    async def check_login_attempt(self, client_address: str) -> RateLimitDecision:
        raise app_exc.AuthProtectionUnavailable


class ConflictingRegistrationAuthService(SuccessfulAuthService):
    async def register(self, data) -> AuthTokens:
        raise app_exc.EmailAlreadyExists


def configure_auth_protection(app: FastAPI) -> AuthProtectionWorkflow:
    protection = AuthProtectionWorkflow()
    app.dependency_overrides[get_anonymous_auth_protection] = lambda: protection
    return protection


@pytest.mark.asyncio
async def test_registration_returns_access_token_and_sets_protected_refresh_cookie() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())
    protection = configure_auth_protection(app)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            headers={"Origin": "https://testserver"},
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
        "token_type": "bearer",
    }
    set_cookie = response.headers["Set-Cookie"]
    assert "task_manager_refresh=refresh-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie
    assert "Max-Age=2592000" in set_cookie
    assert protection.permits[0].confirmed is True
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_failed_registration_releases_reserved_capacity() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(
        AuthService,
        ConflictingRegistrationAuthService(),
    )
    protection = configure_auth_protection(app)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "existing@example.com",
                "password": "correct-password",
                "first_name": "First",
                "last_name": "Last",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "email_already_exists"
    assert protection.permits[0].confirmed is False
    assert protection.permits[0].released is True


@pytest.mark.asyncio
async def test_registration_capacity_limit_rejects_request_before_service_work() -> None:
    app = create_app()
    auth_service = SuccessfulAuthService()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, auth_service)
    protection = configure_auth_protection(app)
    protection.registration_available = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
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

    assert response.status_code == 429
    assert response.json()["code"] == "registration_limit_exceeded"
    assert auth_service.register_calls == 0


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session_without_response_content() -> None:
    app = create_app()
    auth_service = SuccessfulAuthService()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, auth_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        client.cookies.set(
            "task_manager_refresh",
            "refresh-token",
            path="/api/v1/auth",
        )
        response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    assert auth_service.revoked_tokens == ["refresh-token"]
    assert 'task_manager_refresh=""' in response.headers["Set-Cookie"]
    assert "Max-Age=0" in response.headers["Set-Cookie"]
    UUID(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_refresh_rotates_cookie_without_accepting_token_in_request_body() -> None:
    app = create_app()
    auth_service = SuccessfulAuthService()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, auth_service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        client.cookies.set(
            "task_manager_refresh",
            "old-refresh-token",
            path="/api/v1/auth",
        )
        response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "new-access-token",
        "token_type": "bearer",
    }
    assert auth_service.refreshed_tokens == ["old-refresh-token"]
    assert "task_manager_refresh=new-refresh-token" in response.headers["Set-Cookie"]


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_unauthorized_and_expires_cookie() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert 'task_manager_refresh=""' in response.headers["Set-Cookie"]


@pytest.mark.asyncio
async def test_auth_cookie_operations_reject_an_untrusted_browser_origin() -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://attacker.example"},
            json={"email": "user@example.com", "password": "correct-password"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "invalid_request_origin"


@pytest.mark.asyncio
async def test_credentialed_cors_uses_an_explicit_allowed_origin() -> None:
    app = create_app(HTTPConfig(cors_allowed_origins=("https://frontend.example",)))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.options(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://frontend.example"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


@pytest.mark.asyncio
async def test_invalid_credentials_return_safe_unauthorized_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(
        AuthService, InvalidCredentialsAuthService()
    )
    configure_auth_protection(app)

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
async def test_login_rate_limit_returns_retry_boundary_without_checking_credentials() -> None:
    app = create_app()
    auth_service = SuccessfulAuthService()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, auth_service)
    protection = configure_auth_protection(app)
    protection.login_decision = RateLimitDecision(
        allowed=False,
        retry_after_seconds=17,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "correct-password"},
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert response.json()["code"] == "rate_limit_exceeded"
    assert response.json()["context"] == {"retry_after_seconds": 17}
    assert auth_service.login_calls == 0


@pytest.mark.asyncio
async def test_login_fails_closed_when_auth_protection_is_unavailable() -> None:
    app = create_app()
    auth_service = SuccessfulAuthService()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, auth_service)
    app.dependency_overrides[get_anonymous_auth_protection] = lambda: (
        UnavailableAuthProtectionWorkflow()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "correct-password"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "auth_protection_unavailable"
    assert auth_service.login_calls == 0


@pytest.mark.asyncio
async def test_auth_limits_use_address_resolved_through_trusted_proxy() -> None:
    app = create_app(HTTPConfig(trusted_proxy_networks=("127.0.0.0/8",)))
    auth_service = InvalidCredentialsAuthService()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, auth_service)
    protection = configure_auth_protection(app)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
            headers={
                "X-Forwarded-For": "198.51.100.25, 203.0.113.10",
            },
        )

    assert response.status_code == 401
    assert protection.client_addresses == ["203.0.113.10"]


@pytest.mark.asyncio
async def test_request_validation_does_not_echo_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    password = " leaked-password "
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: cast(AuthService, SuccessfulAuthService())
    protection = configure_auth_protection(app)

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
    assert protection.permits[0].confirmed is False
    assert protection.permits[0].released is True
    assert getattr(completion_record, "validation_errors_truncated", None) is False
    assert password not in str(getattr(completion_record, "validation_errors", None))


@pytest.mark.asyncio
async def test_current_user_endpoint_returns_authenticated_user() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
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
        "email_verified": True,
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
async def test_current_user_can_inspect_agent_allowance() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
    )

    async def authenticated_user() -> User:
        return user

    usage = AgentUsageWorkflow()
    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_agent_usage_service] = lambda: cast(
        AgentUsageService,
        usage,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/users/me/agent/usage")

    assert response.status_code == 200
    assert response.json() == {
        "used": usage.allowance.used,
        "access_level": usage.allowance.access_level,
        "limit": usage.allowance.limit,
        "remaining": usage.allowance.remaining,
    }


@pytest.mark.asyncio
async def test_unmetered_agent_allowance_has_no_product_limit() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
    )

    async def authenticated_user() -> User:
        return user

    usage = AgentUsageWorkflow()
    usage.allowance = replace(
        usage.allowance,
        access_level=AgentAccessLevel.UNMETERED,
        limit=None,
        remaining=None,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_agent_usage_service] = lambda: cast(
        AgentUsageService,
        usage,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/users/me/agent/usage")

    assert response.status_code == 200
    assert response.json() == {
        "used": usage.allowance.used,
        "access_level": "unmetered",
        "limit": None,
        "remaining": None,
    }


@pytest.mark.asyncio
async def test_authenticated_request_log_contains_verified_user_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
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
        email_verified=True,
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
            json={"first_name": "Updated"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user.user_id),
        "first_name": "Updated",
        "last_name": "Last",
        "email": "user@example.com",
        "middle_name": None,
        "email_verified": True,
    }


@pytest.mark.asyncio
async def test_profile_update_rejects_email_changes() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
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
            json={"email": "updated@example.com"},
        )

    assert response.status_code == 422
    assert response.json()["details"][0]["code"] == "unexpected_field"


@pytest.mark.asyncio
async def test_authenticated_user_can_clear_optional_profile_field() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
        middle_name="Middle",
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
            json={"middle_name": None},
        )

    assert response.status_code == 200
    assert response.json()["middle_name"] is None


@pytest.mark.asyncio
async def test_user_can_manage_a_task_through_http() -> None:
    user = User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
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
        email_verified=True,
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
        email_verified=True,
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
        email_verified=True,
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
