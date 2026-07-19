from datetime import datetime
from dataclasses import replace
from uuid import UUID, uuid4
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

import exceptions as app_exc
from services.tasks import TaskService
from services.users import UserService
from dto.tasks import (
    AddTaskRecurrenceTemplate,
    UpdateTaskOccurrence,
    UpdateTaskRecurrence,
)
from domain.value_objects.tasks import (
    TaskOccurrence,
    TaskRecurrence,
    TaskRecurrenceTemplate,
)
from domain.value_objects.users import User
from presentation.app import create_app
from presentation.dependencies import (
    get_current_user,
    get_task_service,
    get_user_service,
    require_recurrence_expansion_access,
)


class RecurrenceWorkflowService:
    def __init__(self) -> None:
        self.templates: dict[UUID, TaskRecurrenceTemplate] = {}
        self.rules: dict[UUID, TaskRecurrence] = {}

    async def add_task_recurrence_template(
        self,
        user_id: UUID,
        data: AddTaskRecurrenceTemplate,
    ) -> TaskRecurrenceTemplate:
        template_id = uuid4()
        rules = tuple(
            TaskRecurrence(
                recurrence_id=uuid4(),
                template_id=template_id,
                frequency=item.frequency,
                interval=item.interval,
                anchor_date=item.anchor_date,
                default_time=item.default_time,
                default_duration=item.default_duration,
                weekdays=item.weekdays,
                month_rule=item.month_rule,
                repeat_until=item.repeat_until,
                occurrences_limit=item.occurrences_limit,
            )
            for item in data.rules
        )
        template = TaskRecurrenceTemplate(
            template_id=template_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            created_at=datetime(2026, 7, 13, 12),
            rules=rules,
        )
        self.templates[template_id] = template
        self.rules.update((rule.recurrence_id, rule) for rule in rules)
        return template

    async def get_task_recurrence_templates(self, user_id: UUID, filters):
        return list(self.templates.values())

    async def update_task_recurrence(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        data: UpdateTaskRecurrence,
    ) -> TaskRecurrence:
        updated = replace(
            self.rules[recurrence_id],
            anchor_date=data.anchor_date,
            default_time=data.default_time,
            default_duration=data.default_duration,
            repeat_until=data.repeat_until,
            occurrences_limit=data.occurrences_limit,
        )
        self.rules[recurrence_id] = updated
        return updated

    async def get_task_recurrence_rules(
        self,
        user_id: UUID,
        template_id: UUID,
    ) -> list[TaskRecurrence]:
        return [rule for rule in self.rules.values() if rule.template_id == template_id]

    async def get_task_occurrences(self, user_id: UUID, template_id: UUID, window):
        return [
            TaskOccurrence(
                recurrence_id=rule.recurrence_id,
                task_id=uuid4(),
                original_starts_at=datetime.combine(rule.anchor_date, rule.default_time),
                due_at=rule.due_at,
                schedule=rule.schedule,
            )
            for rule in self.templates[template_id].rules
        ]

    async def update_task_occurrence(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        original_starts_at: datetime,
        data: UpdateTaskOccurrence,
    ) -> TaskOccurrence:
        rule = self.rules[recurrence_id]
        return TaskOccurrence(
            recurrence_id=recurrence_id,
            task_id=None,
            original_starts_at=original_starts_at,
            due_at=data.due_at or data.schedule.ends_at if data.schedule else rule.due_at,
            schedule=data.schedule or rule.schedule,
            is_cancelled=data.is_cancelled,
        )

    async def skip_task_occurrence(
        self,
        user_id: UUID,
        recurrence_id: UUID,
        original_starts_at: datetime,
    ) -> TaskOccurrence:
        rule = self.rules[recurrence_id]
        return TaskOccurrence(
            recurrence_id=recurrence_id,
            task_id=None,
            original_starts_at=original_starts_at,
            due_at=rule.due_at,
            schedule=rule.schedule,
            is_cancelled=True,
        )

    async def delete_task_recurrence(self, user_id: UUID, recurrence_id: UUID) -> None:
        del self.rules[recurrence_id]

    async def delete_task_recurrence_template(self, user_id: UUID, template_id: UUID) -> None:
        template = self.templates.pop(template_id)
        for rule in template.rules:
            self.rules.pop(rule.recurrence_id, None)


class UnverifiedUserService:
    async def require_email_verified(self, user_id: UUID) -> None:
        raise app_exc.EmailVerificationRequired


def _authenticated_user() -> User:
    return User(
        user_id=uuid4(),
        first_name="First",
        last_name="Last",
        email="user@example.com",
        email_verified=True,
    )


@pytest.mark.asyncio
async def test_unverified_user_is_rejected_before_recurrence_creation() -> None:
    user = replace(_authenticated_user(), email_verified=False)
    task_service = RecurrenceWorkflowService()

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_task_service] = lambda: cast(TaskService, task_service)
    app.dependency_overrides[get_user_service] = lambda: cast(
        UserService,
        UnverifiedUserService(),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/recurrence-templates",
            json={
                "title": "Review weekly metrics",
                "rules": [
                    {
                        "frequency": "weekly",
                        "anchor_date": "2026-07-13",
                        "default_time": "09:00:00",
                        "weekdays": [1],
                    }
                ],
            },
        )

    assert response.status_code == 403
    assert response.json()["code"] == "email_verification_required"
    assert task_service.templates == {}


@pytest.mark.asyncio
async def test_user_can_manage_recurring_work_through_http() -> None:
    user = _authenticated_user()
    task_service = RecurrenceWorkflowService()

    async def authenticated_user() -> User:
        return user

    async def allow_recurrence() -> None:
        return None

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_task_service] = lambda: cast(TaskService, task_service)
    app.dependency_overrides[require_recurrence_expansion_access] = allow_recurrence

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/recurrence-templates",
            json={
                "title": "Review weekly metrics",
                "priority": "high",
                "rules": [
                    {
                        "frequency": "weekly",
                        "anchor_date": "2026-07-13",
                        "default_time": "09:00:00",
                        "default_duration": "PT1H",
                        "weekdays": [1],
                    }
                ],
            },
        )
        template_id = created.json()["template_id"]
        recurrence_id = created.json()["rules"][0]["recurrence_id"]
        listed = await client.get(
            "/api/v1/recurrence-templates",
            params={"frequencies": "weekly"},
        )
        updated_rule = await client.patch(
            f"/api/v1/recurrence-rules/{recurrence_id}",
            json={
                "anchor_date": "2026-07-13",
                "default_time": "11:00:00",
                "default_duration": "PT1H",
                "occurrences_limit": 5,
            },
        )
        immutable_update = await client.patch(
            f"/api/v1/recurrence-rules/{recurrence_id}",
            json={
                "anchor_date": "2026-07-13",
                "default_time": "11:00:00",
                "default_duration": "PT1H",
                "occurrences_limit": 5,
                "frequency": "daily",
            },
        )
        occurrences = await client.get(
            f"/api/v1/recurrence-templates/{template_id}/occurrences",
            params={
                "starts_at": "2026-07-13T00:00:00",
                "ends_at": "2026-07-20T00:00:00",
            },
        )
        changed_occurrence = await client.patch(
            f"/api/v1/recurrence-rules/{recurrence_id}/occurrences/2026-07-13T09:00:00",
            json={
                "schedule": {
                    "starts_at": "2026-07-13T13:00:00",
                    "ends_at": "2026-07-13T14:00:00",
                }
            },
        )
        skipped_occurrence = await client.post(
            f"/api/v1/recurrence-rules/{recurrence_id}/occurrences/2026-07-20T09:00:00/skip"
        )
        deleted = await client.delete(f"/api/v1/recurrence-rules/{recurrence_id}")
        rules_after_delete = await client.get(f"/api/v1/recurrence-templates/{template_id}/rules")
        deleted_template = await client.delete(f"/api/v1/recurrence-templates/{template_id}")

    assert created.status_code == 201
    assert created.json()["title"] == "Review weekly metrics"
    assert listed.status_code == 200
    assert [item["template_id"] for item in listed.json()["templates"]] == [template_id]
    assert updated_rule.status_code == 200
    assert updated_rule.json()["schedule"]["starts_at"] == "2026-07-13T11:00:00"
    assert updated_rule.json()["occurrences_limit"] == 5
    assert immutable_update.status_code == 422
    assert immutable_update.json()["code"] == "request_validation_error"
    assert occurrences.status_code == 200
    assert len(occurrences.json()["occurrences"]) == 1
    assert changed_occurrence.status_code == 200
    assert changed_occurrence.json()["schedule"]["starts_at"] == "2026-07-13T13:00:00"
    assert skipped_occurrence.status_code == 200
    assert skipped_occurrence.json()["is_cancelled"] is True
    assert deleted.status_code == 204
    assert rules_after_delete.json()["rules"] == []
    assert deleted_template.status_code == 204


@pytest.mark.asyncio
async def test_recurrence_datetime_with_timezone_is_rejected() -> None:
    user = _authenticated_user()

    async def authenticated_user() -> User:
        return user

    app = create_app()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_task_service] = lambda: cast(
        TaskService,
        RecurrenceWorkflowService(),
    )
    app.dependency_overrides[require_recurrence_expansion_access] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/recurrence-templates",
            json={
                "title": "Review weekly metrics",
                "rules": [
                    {
                        "frequency": "weekly",
                        "anchor_date": "2026-07-13",
                        "default_time": "09:00:00+03:00",
                        "default_duration": "PT1H",
                        "weekdays": [1],
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"
