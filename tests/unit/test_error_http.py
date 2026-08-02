import pytest
import exceptions as app_exc
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from presentation.errors import register_exception_handlers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (app_exc.AuthError("Authentication failed"), 401, "authentication_error"),
        (app_exc.NotFound("Missing resource"), 404, "not_found"),
        (app_exc.Conflict("Conflicting change"), 409, "conflict"),
        (app_exc.Forbidden("Forbidden change"), 403, "forbidden"),
        (app_exc.Wrongness("Invalid change"), 422, "invalid_operation"),
        (app_exc.Unavailable("Dependency unavailable"), 503, "unavailable"),
        (app_exc.BaseAppException("Application failure"), 400, "application_error"),
    ],
)
async def test_application_error_categories_have_stable_http_contracts(
    error: app_exc.BaseAppException,
    expected_status: int,
    expected_code: str,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def fail() -> None:
        raise error

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/failure")

    assert response.status_code == expected_status
    assert response.json() == {
        "code": expected_code,
        "message": str(error),
        "request_id": "unknown",
        "details": [],
    }
    if expected_status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_unexpected_http_error_returns_safe_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def fail() -> None:
        raise RuntimeError("private failure details")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/failure")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_server_error",
        "message": "An unexpected error occurred",
        "request_id": "unknown",
        "details": [],
    }
    assert "private failure details" not in response.text
