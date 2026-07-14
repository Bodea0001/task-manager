from fastapi import APIRouter

from presentation.dependencies import CurrentUserDependency, UserServiceDependency
from presentation.schemas.users import UpdateUserRequest, UserResponse


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: CurrentUserDependency) -> UserResponse:
    return UserResponse.from_domain(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    request: UpdateUserRequest,
    current_user: CurrentUserDependency,
    user_service: UserServiceDependency,
) -> UserResponse:
    user = await user_service.update_user(current_user.user_id, request.to_dto())
    return UserResponse.from_domain(user)
