from asyncio import CancelledError
from logging import DEBUG, ERROR, INFO, WARNING, getLogger
from time import perf_counter
from typing import Literal
from uuid import UUID

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from presentation.request_context import (
    RequestErrorContext,
    get_authenticated_user_id,
    get_request_error,
    get_request_id,
    get_request_log_fields,
)


logger = getLogger(__name__)

type ReadinessTransition = Literal["available", "unavailable"]
type RequestOutcome = Literal["cancelled", "error", "client_error", "success"]


class RequestLoggingMiddleware:
    """Emit one structured completion log for each HTTP request.

    Readiness probes are logged quietly unless their availability changes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._readiness_available: bool | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the application and log the final HTTP outcome."""

        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = get_request_id() or "unknown"
        started_at = perf_counter()
        status_code = 500
        error: BaseException | None = None

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, capture_status)
        except BaseException as exc:
            error = exc
            raise
        finally:
            duration_ms = round((perf_counter() - started_at) * 1_000, 3)
            path, operation, path_params = _get_route_log_fields(scope)
            _log_request_completion(
                request_id=request_id,
                user_id=get_authenticated_user_id(),
                method=scope["method"],
                path=path,
                operation=operation,
                path_params=path_params,
                status_code=status_code,
                duration_ms=duration_ms,
                error=error,
                request_error=get_request_error(),
                request_log_fields=get_request_log_fields(),
                readiness_transition=self._readiness_transition(path, status_code),
            )

    def _readiness_transition(
        self,
        path: str,
        status_code: int,
    ) -> ReadinessTransition | None:
        """Return a readiness transition when the probe state changes."""

        if path != "/health/ready" or status_code not in {200, 503}:
            return None

        is_available = status_code == 200
        previous = self._readiness_available
        self._readiness_available = is_available

        if not is_available and previous is not False:
            return "unavailable"
        if is_available and previous is False:
            return "available"
        return None


def _log_request_completion(
    *,
    request_id: str,
    user_id: UUID | None,
    method: str,
    path: str,
    operation: str | None,
    path_params: dict[str, str],
    status_code: int,
    duration_ms: float,
    error: BaseException | None,
    request_error: RequestErrorContext | None,
    request_log_fields: tuple[tuple[str, object], ...],
    readiness_transition: ReadinessTransition | None,
) -> None:
    """Build and emit the canonical request completion record."""

    outcome = _get_request_outcome(error, status_code)
    message, args, fields = _build_request_log(
        request_id=request_id,
        user_id=user_id,
        method=method,
        path=path,
        operation=operation,
        path_params=path_params,
        status_code=status_code,
        duration_ms=duration_ms,
        outcome=outcome,
    )
    for name, value in request_log_fields:
        fields.setdefault(name, value)

    if error is not None:
        error_type = type(error).__name__
        message += " error_type=%s"
        args += (error_type,)
        fields["error_type"] = error_type

    if request_error is not None:
        message += " error_code=%s"
        args += (request_error.code,)
        fields["error_code"] = request_error.code
        fields.update(request_error.log_fields)

    if readiness_transition is not None:
        message += " readiness_state=%s"
        args += (readiness_transition,)
        fields["readiness_state"] = readiness_transition

    logger.log(
        _get_request_log_level(
            path=path,
            status_code=status_code,
            error=error,
            readiness_transition=readiness_transition,
        ),
        message,
        *args,
        exc_info=(type(error), error, error.__traceback__)
        if error is not None and not isinstance(error, CancelledError)
        else None,
        extra=fields,
    )


def _get_request_outcome(
    error: BaseException | None,
    status_code: int,
) -> RequestOutcome:
    """Classify the request result for structured logging."""

    if isinstance(error, CancelledError):
        return "cancelled"
    if error is not None or status_code >= 500:
        return "error"
    if status_code >= 400:
        return "client_error"
    return "success"


def _build_request_log(
    *,
    request_id: str,
    user_id: UUID | None,
    method: str,
    path: str,
    operation: str | None,
    path_params: dict[str, str],
    status_code: int,
    duration_ms: float,
    outcome: RequestOutcome,
) -> tuple[str, tuple[object, ...], dict[str, object]]:
    """Create the log template, arguments, and structured fields."""

    serialized_user_id = str(user_id) if user_id is not None else None
    display_user_id = serialized_user_id or "null"
    display_operation = operation or "null"
    message = (
        "event=http_request_completed request_id=%s user_id=%s method=%s path=%s operation=%s "
        "status_code=%d duration_ms=%.3f outcome=%s"
    )
    args: tuple[object, ...] = (
        request_id,
        display_user_id,
        method,
        path,
        display_operation,
        status_code,
        duration_ms,
        outcome,
    )
    fields: dict[str, object] = {
        "event": "http_request_completed",
        "request_id": request_id,
        "user_id": serialized_user_id,
        "method": method,
        "path": path,
        "operation": operation,
        "path_params": path_params,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "outcome": outcome,
    }
    return message, args, fields


def _get_route_log_fields(scope: Scope) -> tuple[str, str | None, dict[str, str]]:
    """Return stable route metadata without logging the raw URL."""

    route = scope.get("route")
    path = getattr(route, "path", "<unmatched>")
    operation = getattr(route, "name", None)
    path_params = {name: str(value) for name, value in scope.get("path_params", {}).items()}
    return path, operation, path_params


def _get_request_log_level(
    *,
    path: str,
    status_code: int,
    error: BaseException | None,
    readiness_transition: ReadinessTransition | None,
) -> int:
    """Choose a log level based on failures and health-check state."""

    if isinstance(error, CancelledError):
        return WARNING
    if error is not None:
        return ERROR
    if path == "/health/ready" and status_code == 503:
        return WARNING if readiness_transition == "unavailable" else DEBUG
    if path == "/health/ready" and readiness_transition == "available":
        return INFO
    if path in {"/health/live", "/health/ready"} and status_code < 500:
        return DEBUG
    if status_code >= 500:
        return ERROR
    return INFO
