from dataclasses import dataclass
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue

import exceptions as app_exc
from presentation.request_context import (
    REQUEST_ID_HEADER,
    RequestErrorContext,
    get_request_id,
    set_request_error,
)
from presentation.schemas.common import ErrorDetail, ErrorResponse


_VALIDATION_LOG_DETAIL_LIMIT = 10
_VALIDATION_ERROR_CODES = {
    "missing": "required",
    "extra_forbidden": "unexpected_field",
    "enum": "invalid_choice",
    "literal_error": "invalid_choice",
    "uuid_parsing": "invalid_identifier",
    "uuid_type": "invalid_identifier",
    "timezone_naive": "timezone_not_allowed",
    "datetime_parsing": "invalid_datetime",
    "datetime_from_date_parsing": "invalid_datetime",
    "datetime_type": "invalid_datetime",
    "date_parsing": "invalid_date",
    "date_from_datetime_parsing": "invalid_date",
    "date_type": "invalid_date",
    "bool_parsing": "invalid_boolean",
    "bool_type": "invalid_boolean",
    "int_parsing": "invalid_integer",
    "int_from_float": "invalid_integer",
    "int_type": "invalid_integer",
    "float_parsing": "invalid_number",
    "float_type": "invalid_number",
    "decimal_parsing": "invalid_number",
    "decimal_type": "invalid_number",
    "string_type": "invalid_string",
    "string_too_short": "value_too_short",
    "too_short": "value_too_short",
    "string_too_long": "value_too_long",
    "too_long": "value_too_long",
    "greater_than": "value_too_small",
    "greater_than_equal": "value_too_small",
    "less_than": "value_too_large",
    "less_than_equal": "value_too_large",
    "json_invalid": "invalid_json",
    "value_error": "invalid_value",
    "assertion_error": "invalid_value",
}


@dataclass(frozen=True, slots=True)
class _ErrorDefinition:
    status_code: int
    code: str
    context_fields: tuple[str, ...] = ()


_ERROR_DEFINITIONS: dict[type[app_exc.BaseAppException], _ErrorDefinition] = {
    app_exc.InvalidCredentials: _ErrorDefinition(401, "invalid_credentials"),
    app_exc.InvalidToken: _ErrorDefinition(401, "invalid_token"),
    app_exc.EmailAlreadyExists: _ErrorDefinition(409, "email_already_exists"),
    app_exc.TagAlreadyExists: _ErrorDefinition(409, "tag_already_exists"),
    app_exc.AgentRunInProgress: _ErrorDefinition(409, "agent_run_in_progress"),
    app_exc.AgentCoordinationUnavailable: _ErrorDefinition(
        503,
        "agent_coordination_unavailable",
    ),
    app_exc.EmailVerificationRequired: _ErrorDefinition(403, "email_verification_required"),
    app_exc.AgentQuotaExhausted: _ErrorDefinition(
        403,
        "agent_quota_exhausted",
        ("used", "limit"),
    ),
    app_exc.ChatNotFound: _ErrorDefinition(404, "chat_not_found"),
    app_exc.TagNotFound: _ErrorDefinition(404, "tag_not_found"),
    app_exc.TaskNotFound: _ErrorDefinition(404, "task_not_found"),
    app_exc.UserNotFound: _ErrorDefinition(404, "user_not_found"),
    app_exc.RecurrenceTemplateNotFound: _ErrorDefinition(404, "recurrence_template_not_found"),
    app_exc.RecurrenceRuleNotFound: _ErrorDefinition(404, "recurrence_rule_not_found"),
    app_exc.RecurrenceOccurrenceNotFound: _ErrorDefinition(404, "recurrence_occurrence_not_found"),
    app_exc.WrongTaskInterval: _ErrorDefinition(422, "wrong_task_interval"),
    app_exc.TaskScheduleOverlap: _ErrorDefinition(422, "task_schedule_overlap"),
}


def register_exception_handlers(app: FastAPI) -> None:
    """Register the presentation layer's centralized error translation."""
    app.add_exception_handler(app_exc.BaseAppException, application_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)


async def application_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, app_exc.BaseAppException):
        raise exc
    definition = _error_definition(exc)
    headers = {"WWW-Authenticate": "Bearer"} if definition.status_code == 401 else None
    return _error_response(
        request,
        status_code=definition.status_code,
        code=definition.code,
        message=str(exc),
        headers=headers,
        context={field: getattr(exc, field) for field in definition.context_fields} or None,
    )


async def request_validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = exc.errors()
    details = tuple(
        ErrorDetail(
            location=tuple(error["loc"]),
            code=_validation_error_code(error["type"]),
            message=_validation_error_message(error),
        )
        for error in errors
    )
    log_details = tuple(
        {
            "location": ".".join(str(part) for part in detail.location),
            "code": detail.code,
        }
        for detail in details[:_VALIDATION_LOG_DETAIL_LIMIT]
    )
    return _error_response(
        request,
        status_code=422,
        code="request_validation_error",
        message="Request validation failed",
        details=details,
        log_fields=(
            ("validation_error_count", len(errors)),
            ("validation_errors", log_details),
            ("validation_errors_truncated", len(errors) > len(log_details)),
        ),
    )


def _validation_error_code(error_type: str) -> str:
    return _VALIDATION_ERROR_CODES.get(error_type, "invalid_value")


def _validation_error_message(error: Mapping[str, object]) -> str:
    context = error.get("ctx")
    if isinstance(context, dict):
        cause = context.get("error")
        if isinstance(cause, ValueError):
            return str(cause)

        reason = context.get("reason")
        if isinstance(reason, str):
            return reason

    return str(error["msg"])


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(
        request,
        status_code=500,
        code="internal_server_error",
        message="An unexpected error occurred",
    )


def _error_definition(exc: app_exc.BaseAppException) -> _ErrorDefinition:
    if definition := _ERROR_DEFINITIONS.get(type(exc)):
        return definition
    if isinstance(exc, app_exc.AuthError):
        return _ErrorDefinition(401, "authentication_error")
    if isinstance(exc, app_exc.NotFound):
        return _ErrorDefinition(404, "not_found")
    if isinstance(exc, app_exc.Conflict):
        return _ErrorDefinition(409, "conflict")
    if isinstance(exc, app_exc.Forbidden):
        return _ErrorDefinition(403, "forbidden")
    if isinstance(exc, app_exc.Wrongness):
        return _ErrorDefinition(422, "invalid_operation")
    return _ErrorDefinition(400, "application_error")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: tuple[ErrorDetail, ...] = (),
    headers: dict[str, str] | None = None,
    log_fields: tuple[tuple[str, object], ...] = (),
    context: dict[str, JsonValue] | None = None,
) -> JSONResponse:
    set_request_error(RequestErrorContext(code=code, log_fields=log_fields))
    request_id = getattr(request.state, "request_id", None) or get_request_id() or "unknown"
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = request_id
    body = ErrorResponse(
        code=code,
        message=message,
        request_id=request_id,
        details=details,
        context=context,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=response_headers,
    )
