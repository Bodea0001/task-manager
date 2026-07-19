from fastapi import APIRouter

from presentation.dependencies import (
    AgentUsageServiceDependency,
    CurrentUserDependency,
    UserServiceDependency,
)
from presentation.schemas.users import (
    AgentRunAllowanceResponse,
    UpdateUserRequest,
    UserResponse,
)


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: CurrentUserDependency) -> UserResponse:
    return UserResponse.from_domain(current_user)


@router.get("/me/agent/usage", response_model=AgentRunAllowanceResponse)
async def get_agent_usage(
    current_user: CurrentUserDependency,
    agent_usage_service: AgentUsageServiceDependency,
) -> AgentRunAllowanceResponse:
    allowance = await agent_usage_service.get_allowance(current_user.user_id)
    return AgentRunAllowanceResponse.from_domain(allowance)


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    request: UpdateUserRequest,
    current_user: CurrentUserDependency,
    user_service: UserServiceDependency,
) -> UserResponse:
    user = await user_service.update_user(current_user.user_id, request.to_dto())
    return UserResponse.from_domain(user)
