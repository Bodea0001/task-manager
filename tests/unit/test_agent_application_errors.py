import json
from typing import Any, cast

import pytest
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langchain.agents.middleware import ToolCallRequest

import exceptions as app_exc
from agents.middlewares import ApplicationErrorMiddleware


def _tool_request() -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={
            "name": "restricted_operation",
            "args": {},
            "id": "tool-call-id",
            "type": "tool_call",
        },
        tool=None,
        state={},
        runtime=cast(Any, None),
    )


@pytest.mark.asyncio
async def test_application_error_is_returned_as_an_explainable_tool_result() -> None:
    async def restricted_operation(
        request: ToolCallRequest,
    ) -> ToolMessage | Command[Any]:
        raise app_exc.EmailVerificationRequired

    result = await ApplicationErrorMiddleware().awrap_tool_call(
        _tool_request(),
        restricted_operation,
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "tool-call-id"
    payload = json.loads(str(result.content))
    assert payload["status"] == "forbidden"
    assert payload["code"] == "email_verification_required"
    assert payload["retryable"] is False
    assert "Email verification is required" in payload["message"]
    assert "Verify the account email in settings" in payload["resolution"]
    assert "do not claim the operation succeeded" in payload["instruction"]


@pytest.mark.asyncio
async def test_unexpected_tool_error_is_not_hidden() -> None:
    async def broken_operation(
        request: ToolCallRequest,
    ) -> ToolMessage | Command[Any]:
        raise RuntimeError("unexpected failure")

    with pytest.raises(RuntimeError, match="unexpected failure"):
        await ApplicationErrorMiddleware().awrap_tool_call(
            _tool_request(),
            broken_operation,
        )


@pytest.mark.asyncio
async def test_successful_tool_result_passes_through_unchanged() -> None:
    expected = ToolMessage(
        content='{"status":"ok"}',
        name="restricted_tool",
        tool_call_id="tool-call-id",
    )

    async def successful_operation(
        request: ToolCallRequest,
    ) -> ToolMessage | Command[Any]:
        return expected

    result = await ApplicationErrorMiddleware().awrap_tool_call(
        _tool_request(),
        successful_operation,
    )

    assert result is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "expected_retryable"),
    [
        (app_exc.NotFound("Missing resource"), "not_found", "not_found", False),
        (app_exc.Conflict("Conflicting change"), "conflict", "conflict", False),
        (app_exc.Forbidden("Forbidden change"), "forbidden", "forbidden", False),
        (app_exc.Wrongness("Invalid change"), "invalid_input", "invalid_operation", False),
        (app_exc.Unavailable("Dependency unavailable"), "unavailable", "unavailable", True),
        (app_exc.BaseAppException("Application failure"), "error", "application_error", False),
    ],
)
async def test_application_error_categories_have_stable_safe_tool_contracts(
    error: app_exc.BaseAppException,
    expected_status: str,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    async def failing_operation(
        request: ToolCallRequest,
    ) -> ToolMessage | Command[Any]:
        raise error

    result = await ApplicationErrorMiddleware().awrap_tool_call(
        _tool_request(),
        failing_operation,
    )

    assert isinstance(result, ToolMessage)
    payload = json.loads(str(result.content))
    assert payload["status"] == expected_status
    assert payload["code"] == expected_code
    assert payload["retryable"] is expected_retryable
    assert payload["message"] == str(error)
