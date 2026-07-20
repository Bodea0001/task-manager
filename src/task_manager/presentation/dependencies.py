from asyncio import gather
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import exceptions as app_exc
from agents.app import AgentApplication
from services.auth import AuthService
from services.agent_usage import AgentUsageService
from services.chats import ChatService
from services.tags import TagService
from services.tasks import TaskService
from services.users import UserService
from domain.value_objects.users import User
from presentation.auth_cookies import RefreshTokenCookie
from presentation.container import ApplicationContainer
from presentation.health import is_database_ready, is_key_value_store_ready
from presentation.agent_stream import AgentStreamCoordinator
from presentation.request_context import (
    add_request_log_fields,
    get_request_id,
    set_authenticated_user_id,
)


_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
    description="Task Manager access token.",
)


def get_application_container(request: Request) -> ApplicationContainer:
    """Return resources initialized by the application lifespan."""
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, ApplicationContainer):
        raise RuntimeError("Application resources are not initialized")
    return container


def get_auth_service(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> AuthService:
    return container.auth_service


def get_user_service(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> UserService:
    return container.user_service


def get_agent_usage_service(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> AgentUsageService:
    return container.agent_usage_service


def get_task_service(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> TaskService:
    return container.task_service


def get_tag_service(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> TagService:
    return container.tag_service


def get_chat_service(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> ChatService:
    return container.chat_service


def get_agent_application(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> AgentApplication:
    return container.agent


def get_agent_stream_coordinator(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> AgentStreamCoordinator:
    return container.agent_stream


def get_current_request_id(request: Request) -> str:
    """Return the correlation id assigned by request context middleware."""
    return getattr(request.state, "request_id", None) or get_request_id() or "unknown"


def get_refresh_token_cookie_policy(request: Request) -> RefreshTokenCookie:
    """Return the refresh-cookie policy initialized with the HTTP app."""
    policy = getattr(request.app.state, "refresh_token_cookie", None)
    if not isinstance(policy, RefreshTokenCookie):
        raise RuntimeError("Refresh-token cookie policy is not initialized")
    return policy


def get_refresh_token(
    request: Request,
    cookie: Annotated[RefreshTokenCookie, Depends(get_refresh_token_cookie_policy)],
) -> str:
    """Require the browser-managed refresh token for session rotation."""
    refresh_token = cookie.read(request)
    if refresh_token is None:
        raise app_exc.InvalidToken
    return refresh_token


def get_optional_refresh_token(
    request: Request,
    cookie: Annotated[RefreshTokenCookie, Depends(get_refresh_token_cookie_policy)],
) -> str | None:
    """Return the refresh token when an idempotent logout has one."""
    return cookie.read(request)


def require_trusted_auth_origin(
    request: Request,
    cookie: Annotated[RefreshTokenCookie, Depends(get_refresh_token_cookie_policy)],
) -> None:
    """Apply the browser Origin policy before auth cookie operations."""
    cookie.require_trusted_origin(request)


async def capture_auth_request_metadata(request: Request) -> None:
    """Attach the direct peer address within the request's async context."""
    if request.client is not None:
        add_request_log_fields(client_ip=request.client.host)


async def get_application_readiness(
    container: Annotated[ApplicationContainer, Depends(get_application_container)],
) -> bool:
    """Check resources required before this process should receive traffic."""
    if not container.agent.is_initialized:
        return False
    database_ready, key_value_store_ready = await gather(
        is_database_ready(container.engine),
        is_key_value_store_ready(container.key_value_store_client),
    )
    return database_ready and key_value_store_ready


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """Authenticate a bearer token and return its current user."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise app_exc.InvalidToken

    try:
        user = await auth_service.get_current_user(credentials.credentials)
    except app_exc.UserNotFound:
        raise app_exc.InvalidToken from None

    request.state.user_id = user.user_id
    set_authenticated_user_id(user.user_id)
    return user


async def require_recurrence_expansion_access(
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    """Reject recurrence expansion before entering inner application layers."""
    await user_service.require_email_verified(current_user.user_id)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
AgentUsageServiceDependency = Annotated[AgentUsageService, Depends(get_agent_usage_service)]
UserServiceDependency = Annotated[UserService, Depends(get_user_service)]
TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
TagServiceDependency = Annotated[TagService, Depends(get_tag_service)]
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
AgentApplicationDependency = Annotated[AgentApplication, Depends(get_agent_application)]
AgentStreamCoordinatorDependency = Annotated[
    AgentStreamCoordinator,
    Depends(get_agent_stream_coordinator),
]
RequestIdDependency = Annotated[str, Depends(get_current_request_id)]
CurrentUserDependency = Annotated[User, Depends(get_current_user)]
RefreshTokenCookieDependency = Annotated[
    RefreshTokenCookie,
    Depends(get_refresh_token_cookie_policy),
]
RefreshTokenDependency = Annotated[str, Depends(get_refresh_token)]
OptionalRefreshTokenDependency = Annotated[
    str | None,
    Depends(get_optional_refresh_token),
]
