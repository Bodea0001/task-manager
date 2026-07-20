from fastapi import APIRouter, Depends, Response, status

from presentation.dependencies import (
    AuthServiceDependency,
    RefreshTokenCookieDependency,
    OptionalRefreshTokenDependency,
    RefreshTokenDependency,
    RegistrationPermitDependency,
    capture_auth_request_metadata,
    enforce_login_rate_limit,
    require_trusted_auth_origin,
)
from presentation.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RegisterUserRequest,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    dependencies=[
        Depends(capture_auth_request_metadata),
        Depends(require_trusted_auth_origin),
    ],
)


@router.post("/register", response_model=AccessTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: RegisterUserRequest,
    response: Response,
    auth_service: AuthServiceDependency,
    refresh_cookie: RefreshTokenCookieDependency,
    registration_permit: RegistrationPermitDependency,
) -> AccessTokenResponse:
    tokens = await auth_service.register(request.to_dto())
    await registration_permit.confirm()
    refresh_cookie.set(response, tokens.refresh_token, auth_service.refresh_token_ttl)
    return AccessTokenResponse.from_domain(tokens)


@router.post(
    "/login",
    response_model=AccessTokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(
    request: LoginRequest,
    response: Response,
    auth_service: AuthServiceDependency,
    refresh_cookie: RefreshTokenCookieDependency,
) -> AccessTokenResponse:
    tokens = await auth_service.login(request.to_dto())
    refresh_cookie.set(response, tokens.refresh_token, auth_service.refresh_token_ttl)
    return AccessTokenResponse.from_domain(tokens)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_tokens(
    response: Response,
    refresh_token: RefreshTokenDependency,
    auth_service: AuthServiceDependency,
    refresh_cookie: RefreshTokenCookieDependency,
) -> AccessTokenResponse:
    tokens = await auth_service.refresh(refresh_token)
    refresh_cookie.set(response, tokens.refresh_token, auth_service.refresh_token_ttl)
    return AccessTokenResponse.from_domain(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    refresh_token: OptionalRefreshTokenDependency,
    auth_service: AuthServiceDependency,
    refresh_cookie: RefreshTokenCookieDependency,
) -> Response:
    if refresh_token is not None:
        await auth_service.revoke_refresh_token(refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    refresh_cookie.clear(response)
    return response
