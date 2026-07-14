from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


REQUEST_ID_HEADER = "X-Request-ID"


@dataclass(frozen=True, slots=True)
class RequestErrorContext:
    """Safe structured error metadata for the request completion log."""

    code: str
    log_fields: tuple[tuple[str, object], ...] = ()


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_authenticated_user_id: ContextVar[UUID | None] = ContextVar("authenticated_user_id", default=None)
_request_error: ContextVar[RequestErrorContext | None] = ContextVar(
    "request_error",
    default=None,
)
_request_log_fields: ContextVar[tuple[tuple[str, object], ...]] = ContextVar(
    "request_log_fields",
    default=(),
)


@contextmanager
def bind_request_context(request_id: str) -> Generator[None]:
    """Bind fresh correlation data for one request and restore prior context afterward."""
    request_id_token = _request_id.set(request_id)
    user_id_token = _authenticated_user_id.set(None)
    error_token = _request_error.set(None)
    log_fields_token = _request_log_fields.set(())
    try:
        yield
    finally:
        _request_log_fields.reset(log_fields_token)
        _request_error.reset(error_token)
        _authenticated_user_id.reset(user_id_token)
        _request_id.reset(request_id_token)


def get_request_id() -> str | None:
    """Return the request id bound to the current async execution context."""
    return _request_id.get()


def set_authenticated_user_id(user_id: UUID) -> None:
    """Bind an identity after successful authentication for request observability."""
    _authenticated_user_id.set(user_id)


def get_authenticated_user_id() -> UUID | None:
    """Return the verified user id bound to the current request, if available."""
    return _authenticated_user_id.get()


def set_request_error(error: RequestErrorContext) -> None:
    """Bind safe error metadata produced while handling the current request."""
    _request_error.set(error)


def get_request_error() -> RequestErrorContext | None:
    """Return safe error metadata for the current request, if any."""
    return _request_error.get()


def add_request_log_fields(**fields: object) -> None:
    """Add safe structured fields to the current request completion log."""
    _request_log_fields.set((*_request_log_fields.get(), *fields.items()))


def get_request_log_fields() -> tuple[tuple[str, object], ...]:
    """Return additional structured fields bound to the current request."""
    return _request_log_fields.get()
