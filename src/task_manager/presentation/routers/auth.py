from fastapi import APIRouter, Depends, status

from presentation.dependencies import AuthServiceDependency, capture_auth_request_metadata
from presentation.schemas.auth import (
    AuthTokensResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterUserRequest,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    dependencies=[Depends(capture_auth_request_metadata)],
)


@router.post("/register", response_model=AuthTokensResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: RegisterUserRequest,
    auth_service: AuthServiceDependency,
) -> AuthTokensResponse:
    tokens = await auth_service.register(request.to_dto())
    return AuthTokensResponse.from_domain(tokens)


@router.post("/login", response_model=AuthTokensResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthServiceDependency,
) -> AuthTokensResponse:
    tokens = await auth_service.login(request.to_dto())
    return AuthTokensResponse.from_domain(tokens)


@router.post("/refresh", response_model=AuthTokensResponse)
async def refresh_tokens(
    request: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
) -> AuthTokensResponse:
    tokens = await auth_service.refresh(request.refresh_token.get_secret_value())
    return AuthTokensResponse.from_domain(tokens)
