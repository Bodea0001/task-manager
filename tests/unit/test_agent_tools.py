from types import SimpleNamespace
from typing import Any, cast
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import exceptions as app_exc
from agents.schemas.tools import AddTaskRecurrenceData, RecurrenceMonthRuleData
from agents.tools import tags as tag_tools
from agents.tools import tasks as task_tools
from domain.value_objects.audit import AuditEntityType, AuditEvent, AuditEventType
from domain.value_objects.tags import Tag
from domain.value_objects.tasks import (
    FreeTime,
    RecurrenceFrequency,
    RecurrenceMonthRule,
    Schedule,
    ScheduleAvailability,
    Task,
    TaskOccurrence,
    TaskPriority,
    TaskRecurrence,
    TaskRecurrenceTemplate,
    TaskStatus,
    Weekday,
)
from dto.tasks import TaskList
from services.tags import TagService
from services.tasks import TaskService


NOW = datetime(2099, 1, 2, 10, 0)


def _tool_fixture():
    user_id = uuid4()
    task_id = uuid4()
    tag_id = uuid4()
    template_id = uuid4()
    recurrence_id = uuid4()
    schedule = Schedule(starts_at=NOW, ends_at=NOW + timedelta(hours=1))
    tag = Tag(tag_id=tag_id, name="work", created_at=NOW)
    task = Task(
        task_id=task_id,
        title="Prepare report",
        description="Send the final report",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.HIGH,
        due_at=schedule.ends_at,
        created_at=NOW - timedelta(days=1),
        completed_at=NOW,
        schedule=schedule,
        tags=[tag],
    )
    rule = TaskRecurrence(
        recurrence_id=recurrence_id,
        template_id=template_id,
        frequency=RecurrenceFrequency.MONTHLY,
        interval=1,
        anchor_date=NOW.date(),
        default_time=NOW.time(),
        default_duration=timedelta(hours=1),
        month_rule=RecurrenceMonthRule(week_of_month=-1, weekday=Weekday.FRIDAY),
        occurrences_limit=3,
    )
    template = TaskRecurrenceTemplate(
        template_id=template_id,
        title="Monthly report",
        description="Prepare a monthly report",
        priority=TaskPriority.HIGH,
        created_at=NOW,
        tags=[tag],
        rules=(rule,),
    )
    occurrence = TaskOccurrence(
        recurrence_id=recurrence_id,
        task_id=task_id,
        original_starts_at=schedule.starts_at,
        due_at=schedule.ends_at,
        schedule=schedule,
    )
    event = AuditEvent(
        event_id=uuid4(),
        actor_user_id=user_id,
        entity_type=AuditEntityType.TASK,
        entity_id=task_id,
        event_type=AuditEventType.TASK_UPDATED,
        occurred_at=NOW,
        data={"changed_fields": ["status"]},
    )

    task_service = AsyncMock(spec=TaskService)
    task_service.get_task.return_value = task
    task_service.get_tasks.return_value = TaskList(tasks=[task], conflicts=[task])
    task_service.count_tasks.return_value = 1
    task_service.get_overdue_tasks.return_value = [task]
    task_service.create_task.return_value = task
    task_service.update_task.return_value = task
    task_service.complete_task.return_value = task
    task_service.reopen_task.return_value = task
    task_service.cancel_task.return_value = task
    task_service.get_task_history.return_value = [event]
    task_service.get_free_time.return_value = [FreeTime(NOW, NOW + timedelta(minutes=30))]
    task_service.check_schedule_availability.return_value = ScheduleAvailability(
        can_add_task=False,
        blocking_tasks=[task],
    )
    task_service.find_nearest_free_schedule.return_value = schedule
    task_service.delete_schedule_from_task.return_value = task
    task_service.add_tag_to_task.return_value = task
    task_service.delete_tag_from_task.return_value = task
    task_service.get_task_recurrence_template.return_value = template
    task_service.get_task_recurrence_templates.return_value = [template]
    task_service.count_task_recurrence_templates.return_value = 1
    task_service.add_task_recurrence_template.return_value = template
    task_service.get_task_recurrence_rules.return_value = [rule]
    task_service.add_task_recurrence_rule.return_value = rule
    task_service.update_task_recurrence.return_value = rule
    task_service.stop_task_recurrence.return_value = rule
    task_service.get_task_occurrences.return_value = [occurrence]
    task_service.get_recurrence_instance_by_task_id.return_value = occurrence
    task_service.update_task_occurrence.return_value = occurrence
    task_service.skip_task_occurrence.return_value = occurrence
    task_service.get_task_recurrence_template_history.return_value = [event]
    task_service.add_tag_to_task_recurrence_template.return_value = template
    task_service.delete_tag_from_task_recurrence_template.return_value = template

    tag_service = AsyncMock(spec=TagService)
    tag_service.get_tags.return_value = [tag]
    tag_service.get_tag.return_value = tag
    tag_service.get_tag_history.return_value = [event]
    tag_service.create_tag.return_value = tag
    tag_service.ensure_tag.return_value = tag
    tag_service.update_tag.return_value = tag

    runtime = SimpleNamespace(
        context=SimpleNamespace(
            user_id=user_id,
            task_service=task_service,
            tag_service=tag_service,
        )
    )
    return SimpleNamespace(
        runtime=runtime,
        user_id=user_id,
        task_id=task_id,
        tag_id=tag_id,
        template_id=template_id,
        recurrence_id=recurrence_id,
        schedule=schedule,
        task=task,
        rule=rule,
        template=template,
        occurrence=occurrence,
        event=event,
        task_service=task_service,
        tag_service=tag_service,
    )


async def _invoke(tool: Any, runtime: Any, **kwargs: Any) -> dict[str, Any]:
    return await cast(Any, tool).coroutine(runtime=runtime, **kwargs)


@pytest.mark.asyncio
async def test_task_tools_expose_task_and_schedule_workflows() -> None:
    fixture = _tool_fixture()
    calls = (
        (task_tools.get_task, {"task_id": fixture.task_id}, "task"),
        (task_tools.list_tasks, {"search_text": "report"}, "tasks"),
        (task_tools.count_tasks, {"search_text": "report"}, "count"),
        (task_tools.get_overdue_tasks, {}, "tasks"),
        (
            task_tools.create_task,
            {
                "title": fixture.task.title,
                "due_at": fixture.task.due_at,
                "description": fixture.task.description,
                "priority": fixture.task.priority,
                "schedule": fixture.schedule,
            },
            "task",
        ),
        (
            task_tools.update_task,
            {"task_id": fixture.task_id, "title": "Updated report"},
            "task",
        ),
        (task_tools.complete_task, {"task_id": fixture.task_id}, "task"),
        (task_tools.reopen_task, {"task_id": fixture.task_id}, "task"),
        (task_tools.cancel_task, {"task_id": fixture.task_id}, "task"),
        (task_tools.get_task_history, {"task_id": fixture.task_id}, "events"),
        (
            task_tools.update_task_schedule,
            {"task_id": fixture.task_id, "schedule": fixture.schedule},
            "task",
        ),
        (task_tools.get_free_time, {"windows": (fixture.schedule,)}, "free_time"),
        (
            task_tools.check_schedule_availability,
            {"window": fixture.schedule},
            "availability",
        ),
        (
            task_tools.find_nearest_free_schedule,
            {"duration_minutes": 30, "search_from": NOW},
            "schedule",
        ),
        (task_tools.delete_task_schedule, {"task_id": fixture.task_id}, "task"),
        (
            task_tools.add_tag_to_task,
            {"task_id": fixture.task_id, "tag_id": fixture.tag_id},
            "task",
        ),
        (
            task_tools.remove_tag_from_task,
            {"task_id": fixture.task_id, "tag_id": fixture.tag_id},
            "task",
        ),
    )

    for tool, kwargs, result_field in calls:
        result = await _invoke(tool, fixture.runtime, **kwargs)
        assert result["status"] == "ok"
        assert result_field in result

    listed = await _invoke(task_tools.list_tasks, fixture.runtime)
    assert listed["tasks"][0]["completed_at"] == NOW.isoformat()
    assert listed["tasks"][0]["schedule"] == {
        "starts_at": fixture.schedule.starts_at.isoformat(),
        "ends_at": fixture.schedule.ends_at.isoformat(),
    }
    assert listed["conflicts"][0]["task_id"] == str(fixture.task_id)


@pytest.mark.asyncio
async def test_recurrence_tools_expose_template_rule_and_occurrence_workflows() -> None:
    fixture = _tool_fixture()
    month_rule = RecurrenceMonthRuleData(week_of_month=-1, weekday=Weekday.FRIDAY)
    rule_data = AddTaskRecurrenceData(
        frequency=RecurrenceFrequency.MONTHLY,
        anchor_date=NOW.date(),
        default_time=NOW.time(),
        default_duration=timedelta(hours=1),
        month_rule=month_rule,
        occurrences_limit=3,
    )
    calls = (
        (
            task_tools.get_task_recurrence_template,
            {"template_id": fixture.template_id},
            "template",
        ),
        (task_tools.list_task_recurrence_templates, {}, "templates"),
        (task_tools.count_task_recurrence_templates, {}, "count"),
        (
            task_tools.create_task_recurrence_template,
            {"title": fixture.template.title, "rules": (rule_data,)},
            "template",
        ),
        (
            task_tools.get_task_recurrence_rules,
            {"template_id": fixture.template_id},
            "rules",
        ),
        (
            task_tools.add_task_recurrence_rule,
            {
                "template_id": fixture.template_id,
                "frequency": RecurrenceFrequency.MONTHLY,
                "anchor_date": NOW.date(),
                "default_time": NOW.time(),
                "default_duration": timedelta(hours=1),
                "month_rule": month_rule,
                "occurrences_limit": 3,
            },
            "rule",
        ),
        (
            task_tools.update_task_recurrence_rule,
            {
                "recurrence_id": fixture.recurrence_id,
                "anchor_date": NOW.date(),
                "default_time": NOW.time(),
                "default_duration": timedelta(hours=1),
                "occurrences_limit": 3,
            },
            "rule",
        ),
        (
            task_tools.stop_task_recurrence,
            {"recurrence_id": fixture.recurrence_id, "stop_from": NOW},
            "rule",
        ),
        (
            task_tools.get_task_occurrences,
            {"template_id": fixture.template_id, "window": fixture.schedule},
            "occurrences",
        ),
        (
            task_tools.get_recurrence_instance_by_task,
            {"task_id": fixture.task_id},
            "occurrence",
        ),
        (
            task_tools.update_task_occurrence,
            {
                "recurrence_id": fixture.recurrence_id,
                "original_starts_at": NOW,
                "title": "Updated occurrence",
            },
            "occurrence",
        ),
        (
            task_tools.skip_task_occurrence,
            {"recurrence_id": fixture.recurrence_id, "original_starts_at": NOW},
            "occurrence",
        ),
        (
            task_tools.get_task_recurrence_template_history,
            {"template_id": fixture.template_id},
            "events",
        ),
        (
            task_tools.add_tag_to_recurrence_template,
            {"template_id": fixture.template_id, "tag_id": fixture.tag_id},
            "template",
        ),
        (
            task_tools.remove_tag_from_recurrence_template,
            {"template_id": fixture.template_id, "tag_id": fixture.tag_id},
            "template",
        ),
    )

    for tool, kwargs, result_field in calls:
        result = await _invoke(tool, fixture.runtime, **kwargs)
        assert result["status"] == "ok"
        assert result_field in result

    template_result = await _invoke(
        task_tools.get_task_recurrence_template,
        fixture.runtime,
        template_id=fixture.template_id,
    )
    serialized_rule = template_result["template"]["rules"][0]
    assert serialized_rule["month_rule"] == {
        "month_day": None,
        "week_of_month": -1,
        "weekday": int(Weekday.FRIDAY),
        "business_day_policy": "none",
    }
    assert serialized_rule["default_duration_seconds"] == 3600


@pytest.mark.asyncio
async def test_tag_tools_expose_tag_workflows() -> None:
    fixture = _tool_fixture()
    calls = (
        (tag_tools.list_tags, {}, "tags"),
        (tag_tools.get_tag, {"tag_id": fixture.tag_id}, "tag"),
        (tag_tools.get_tag_history, {"tag_id": fixture.tag_id}, "events"),
        (tag_tools.create_tag, {"name": "work"}, "tag"),
        (tag_tools.ensure_tag, {"name": "work"}, "tag"),
        (tag_tools.update_tag, {"tag_id": fixture.tag_id, "name": "office"}, "tag"),
    )

    for tool, kwargs, result_field in calls:
        result = await _invoke(tool, fixture.runtime, **kwargs)
        assert result["status"] == "ok"
        assert result_field in result

    listed = await _invoke(tag_tools.list_tags, fixture.runtime)
    assert listed == {
        "status": "ok",
        "count": 1,
        "tags": [
            {
                "tag_id": str(fixture.tag_id),
                "name": "work",
                "created_at": NOW.isoformat(),
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "service_name", "service_method", "error", "kwargs", "expected_status"),
    [
        (
            task_tools.get_task,
            "task_service",
            "get_task",
            app_exc.TaskNotFound(),
            {"task_id": uuid4()},
            "not_found",
        ),
        (
            task_tools.create_task,
            "task_service",
            "create_task",
            app_exc.TaskScheduleOverlap(),
            {"title": "Conflict", "due_at": NOW},
            "conflict",
        ),
        (
            task_tools.update_task,
            "task_service",
            "update_task",
            app_exc.TaskNotFound(),
            {"task_id": uuid4(), "title": "Updated"},
            "not_found",
        ),
        (
            task_tools.update_task_schedule,
            "task_service",
            "update_task",
            app_exc.TaskScheduleOverlap(),
            {"task_id": uuid4(), "schedule": Schedule(NOW, NOW + timedelta(hours=1))},
            "conflict",
        ),
        (
            task_tools.get_task_recurrence_template,
            "task_service",
            "get_task_recurrence_template",
            app_exc.RecurrenceTemplateNotFound(),
            {"template_id": uuid4()},
            "not_found",
        ),
        (
            task_tools.create_task_recurrence_template,
            "task_service",
            "add_task_recurrence_template",
            app_exc.TagNotFound(),
            {
                "title": "Recurring task",
                "tag_ids": (uuid4(),),
                "rules": (
                    AddTaskRecurrenceData(
                        frequency=RecurrenceFrequency.DAILY,
                        anchor_date=NOW.date(),
                        default_time=NOW.time(),
                    ),
                ),
            },
            "not_found",
        ),
        (
            task_tools.add_task_recurrence_rule,
            "task_service",
            "add_task_recurrence_rule",
            app_exc.RecurrenceTemplateNotFound(),
            {
                "template_id": uuid4(),
                "frequency": RecurrenceFrequency.DAILY,
                "anchor_date": NOW.date(),
                "default_time": NOW.time(),
            },
            "not_found",
        ),
        (
            task_tools.update_task_recurrence_rule,
            "task_service",
            "update_task_recurrence",
            app_exc.RecurrenceRuleNotFound(),
            {
                "recurrence_id": uuid4(),
                "anchor_date": NOW.date(),
                "default_time": time(10, 0),
            },
            "not_found",
        ),
        (
            task_tools.stop_task_recurrence,
            "task_service",
            "stop_task_recurrence",
            app_exc.RecurrenceRuleNotFound(),
            {"recurrence_id": uuid4(), "stop_from": NOW},
            "not_found",
        ),
        (
            task_tools.get_task_occurrences,
            "task_service",
            "get_task_occurrences",
            app_exc.RecurrenceTemplateNotFound(),
            {
                "template_id": uuid4(),
                "window": Schedule(NOW, NOW + timedelta(hours=1)),
            },
            "not_found",
        ),
        (
            task_tools.update_task_occurrence,
            "task_service",
            "update_task_occurrence",
            app_exc.RecurrenceRuleNotFound(),
            {"recurrence_id": uuid4(), "original_starts_at": NOW, "title": "Updated"},
            "not_found",
        ),
        (
            task_tools.add_tag_to_recurrence_template,
            "task_service",
            "add_tag_to_task_recurrence_template",
            app_exc.TagNotFound(),
            {"template_id": uuid4(), "tag_id": uuid4()},
            "not_found",
        ),
        (
            tag_tools.get_tag,
            "tag_service",
            "get_tag",
            app_exc.TagNotFound(),
            {"tag_id": uuid4()},
            "not_found",
        ),
        (
            tag_tools.get_tag_history,
            "tag_service",
            "get_tag_history",
            app_exc.TagNotFound(),
            {"tag_id": uuid4()},
            "not_found",
        ),
        (
            tag_tools.create_tag,
            "tag_service",
            "create_tag",
            ValueError("name cannot be empty"),
            {"name": ""},
            "invalid_input",
        ),
        (
            tag_tools.update_tag,
            "tag_service",
            "update_tag",
            app_exc.TagNotFound(),
            {"tag_id": uuid4(), "name": "office"},
            "not_found",
        ),
    ],
)
async def test_agent_tools_return_safe_expected_errors(
    tool: Any,
    service_name: str,
    service_method: str,
    error: Exception,
    kwargs: dict[str, Any],
    expected_status: str,
) -> None:
    fixture = _tool_fixture()
    service = getattr(fixture, service_name)
    getattr(service, service_method).side_effect = error

    result = await _invoke(tool, fixture.runtime, **kwargs)

    assert result["status"] == expected_status
    assert result["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [task_tools.list_tasks, task_tools.count_tasks])
async def test_task_lookup_tools_reject_invalid_filters_without_service_work(tool: Any) -> None:
    fixture = _tool_fixture()

    result = await _invoke(
        tool,
        fixture.runtime,
        due_from=NOW,
        due_to=NOW - timedelta(days=1),
    )

    assert result["status"] == "invalid_input"
    assert result["retryable"] is False
    fixture.task_service.get_tasks.assert_not_awaited()
    fixture.task_service.count_tasks.assert_not_awaited()
