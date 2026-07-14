from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from presentation.request_context import REQUEST_ID_HEADER, bind_request_context

_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("ascii")


class RequestContextMiddleware:
    """Bind correlation data for the lifetime of each HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _get_or_create_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with bind_request_context(request_id):
            await self._app(scope, receive, send_with_request_id)


def _get_or_create_request_id(scope: Scope) -> str:
    for name, value in scope["headers"]:
        if name != _REQUEST_ID_HEADER_BYTES:
            continue
        try:
            return str(UUID(value.decode("ascii")))
        except UnicodeDecodeError, ValueError:
            break

    return str(uuid4())
