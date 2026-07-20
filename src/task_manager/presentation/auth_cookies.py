from datetime import timedelta
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Request, Response

import exceptions as app_exc
from config import HTTPConfig


class RefreshTokenCookie:
    """Apply one configured transport policy to refresh-token cookies."""

    def __init__(self, config: HTTPConfig) -> None:
        self._name = config.refresh_token_cookie_name
        self._path = config.refresh_token_cookie_path
        self._secure = config.refresh_token_cookie_secure
        self._same_site: Literal["lax", "strict"] = config.refresh_token_cookie_same_site
        self._allowed_origins = frozenset(config.cors_allowed_origins)

    def read(self, request: Request) -> str | None:
        """Read the opaque refresh token without exposing it to schemas."""
        return request.cookies.get(self._name)

    def set(self, response: Response, refresh_token: str, ttl: timedelta) -> None:
        """Store a host-only refresh token with browser-enforced protections."""
        response.set_cookie(
            key=self._name,
            value=refresh_token,
            max_age=int(ttl.total_seconds()),
            path=self._path,
            secure=self._secure,
            httponly=True,
            samesite=self._same_site,
        )

    def clear(self, response: Response) -> None:
        """Expire the cookie using the same name and path that created it."""
        response.delete_cookie(key=self._name, path=self._path)

    def is_refresh_path(self, path: str) -> bool:
        """Return whether a response belongs to the cookie rotation endpoint."""
        return path == f"{self._path}/refresh"

    def require_trusted_origin(self, request: Request) -> None:
        """Reject browser cookie operations initiated by an untrusted origin."""
        origin = request.headers.get("origin")
        if origin is None:
            return

        normalized_origin = origin.rstrip("/")
        if normalized_origin in self._allowed_origins:
            return

        parsed_origin = urlsplit(normalized_origin)
        request_host = request.headers.get("host", "").lower()
        if (
            parsed_origin.scheme in {"http", "https"}
            and parsed_origin.netloc.lower() == request_host
            and not parsed_origin.path
            and not parsed_origin.query
            and not parsed_origin.fragment
        ):
            return

        raise app_exc.InvalidRequestOrigin
