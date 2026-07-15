from fastapi import APIRouter, Depends, Response, status

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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
) -> Response:
    await auth_service.revoke_refresh_token(request.refresh_token.get_secret_value())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
