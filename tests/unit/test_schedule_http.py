from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from services.tasks import TaskService
from domain.value_objects.tasks import (
    FreeTime,
    Schedule,
    ScheduleAvailability,
    Task,
    TaskPriority,
    TaskStatus,
)
from domain.value_objects.users import User
from presentation.app import create_app
from presentation.dependencies import get_current_user, get_task_service


class ScheduleWorkflowService:
    async def get_free_time(
        self,
        user_id: UUID,
        windows: tuple[Schedule, ...],
    ) -> list[FreeTime]:
        window = windows[0]
        return [
            FreeTime(
                starts_at=window.starts_at + timedelta(hours=1),
                ends_at=window.ends_at,
            )
        ]

    async def check_schedule_availability(
        self,
        user_id: UUID,
        window: Schedule,
    ) -> ScheduleAvailability:
        blocking_task = Task(
            task_id=uuid4(),
            title="Existing appointment",
            status=TaskStatus.ACTIVE,
            priority=TaskPriority.NORMAL,
            due_at=window.ends_at,
            created_at=datetime(2026, 7, 13, 8),
            schedule=window,
        )
        return ScheduleAvailability(can_add_task=False, blocking_tasks=[blocking_task])

    async def find_nearest_free_schedule(
        self,
        user_id: UUID,
        duration: timedelta,
        excluded_windows: tuple[Schedule, ...] = (),
        search_from: datetime | None = None,
    ) -> Schedule:
        starts_at = search_from or datetime(2026, 7, 13, 9)
        return Schedule(starts_at=starts_at, ends_at=starts_at + duration)


def _authenticated_user() -> User:
    return User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
    )


def _create_schedule_app():
    user = _authenticated_user()

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_task_service] = lambda: cast(
        TaskService,
        ScheduleWorkflowService(),
    )
    return app


@pytest.mark.asyncio
async def test_user_can_inspect_schedule_through_http() -> None:
    app = _create_schedule_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        free_time = await client.post(
            "/api/v1/schedules/free-time",
            json={
                "windows": [
                    {
                        "starts_at": "2026-07-13T09:00:00",
                        "ends_at": "2026-07-13T12:00:00",
                    }
                ]
            },
        )
        availability = await client.post(
            "/api/v1/schedules/availability",
            json={
                "window": {
                    "starts_at": "2026-07-13T09:00:00",
                    "ends_at": "2026-07-13T10:00:00",
                }
            },
        )
        nearest = await client.post(
            "/api/v1/schedules/nearest-free",
            json={
                "duration_minutes": 45,
                "search_from": "2026-07-13T13:00:00",
                "excluded_windows": [],
            },
        )

    assert free_time.status_code == 200
    assert free_time.json() == {
        "free_time": [
            {
                "starts_at": "2026-07-13T10:00:00",
                "ends_at": "2026-07-13T12:00:00",
            }
        ]
    }
    assert availability.status_code == 200
    assert availability.json()["can_add_task"] is False
    assert [task["title"] for task in availability.json()["blocking_tasks"]] == [
        "Existing appointment"
    ]
    assert nearest.status_code == 200
    assert nearest.json() == {
        "schedule": {
            "starts_at": "2026-07-13T13:00:00",
            "ends_at": "2026-07-13T13:45:00",
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, payload",
    (
        ("/api/v1/schedules/free-time", {"windows": []}),
        (
            "/api/v1/schedules/availability",
            {
                "window": {
                    "starts_at": "2026-07-13T10:00:00+03:00",
                    "ends_at": "2026-07-13T11:00:00+03:00",
                }
            },
        ),
        ("/api/v1/schedules/nearest-free", {"duration_minutes": 0}),
    ),
)
async def test_invalid_schedule_request_is_rejected(path: str, payload: dict) -> None:
    app = _create_schedule_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(path, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"
