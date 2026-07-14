from logging import getLogger

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import HTTPConfig, settings
from presentation.errors import register_exception_handlers
from presentation.lifespan import application_lifespan
from presentation.middlewares import RequestContextMiddleware, RequestLoggingMiddleware
from presentation.routers import routers, unversioned_routers


APP_TITLE = "Task Manager"
APP_VERSION = "0.1.0"

logger = getLogger(__name__)


def create_app(config: HTTPConfig | None = None) -> FastAPI:
    """Create the Task Manager HTTP application without opening resources."""
    http_config = config or settings.http
    docs_url = "/docs" if http_config.docs_enabled else None
    openapi_url = "/openapi.json" if http_config.docs_enabled else None
    redoc_url = "/redoc" if http_config.docs_enabled else None

    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        docs_url=docs_url,
        openapi_url=openapi_url,
        redoc_url=redoc_url,
        lifespan=application_lifespan,
    )
    register_exception_handlers(app)
    for router in unversioned_routers:
        app.include_router(router)
    for router in routers:
        app.include_router(router, prefix=http_config.api_prefix)
    _configure_middleware(app, http_config)
    logger.debug(
        "event=http_application_configured api_prefix=%s docs_enabled=%s "
        "router_count=%d cors_enabled=%s trusted_hosts_enabled=%s",
        http_config.api_prefix,
        http_config.docs_enabled,
        len(routers) + len(unversioned_routers),
        bool(http_config.cors_allowed_origins),
        bool(http_config.trusted_hosts),
        extra={
            "event": "http_application_configured",
            "api_prefix": http_config.api_prefix,
            "docs_enabled": http_config.docs_enabled,
            "router_count": len(routers) + len(unversioned_routers),
            "cors_enabled": bool(http_config.cors_allowed_origins),
            "trusted_hosts_enabled": bool(http_config.trusted_hosts),
        },
    )
    return app


def _configure_middleware(app: FastAPI, config: HTTPConfig) -> None:
    if config.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.cors_allowed_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if config.trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=list(config.trusted_hosts),
        )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
