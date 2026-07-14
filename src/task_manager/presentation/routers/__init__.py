from fastapi import APIRouter

from presentation.routers.auth import router as auth_router
from presentation.routers.agent import router as agent_router
from presentation.routers.chats import router as chats_router
from presentation.routers.health import router as health_router
from presentation.routers.recurrences import router as recurrences_router
from presentation.routers.schedules import router as schedules_router
from presentation.routers.tags import router as tags_router
from presentation.routers.tasks import router as tasks_router
from presentation.routers.users import router as users_router


routers: list[APIRouter] = [
    auth_router,
    agent_router,
    users_router,
    tasks_router,
    schedules_router,
    chats_router,
    tags_router,
    recurrences_router,
]
unversioned_routers: list[APIRouter] = [health_router]


__all__ = ["routers", "unversioned_routers"]
