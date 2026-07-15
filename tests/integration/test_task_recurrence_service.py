from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from config import settings
from constants import TEST_OTHER_USER_ID, TEST_TITLE_PREFIX, TEST_USER_ID
from domain.value_objects.audit import AuditEventType
from domain.value_objects.tasks import (
    FreeTime,
    RecurrenceBusinessDayPolicy,
    RecurrenceFrequency,
    RecurrenceMonthRule,
    Schedule,
    Task,
    TaskKind,
    TaskPriority,
    TaskStatus,
    Weekday,
)
from dto.tasks import (
    AddTask,
    AddTaskRecurrence,
    AddTaskRecurrenceTemplate,
    ListTaskRecurrenceTemplatesFilters,
    ListTasksFilters,
    UpdateTaskRecurrence,
    UpdateTaskData,
    UpdateTaskOccurrence,
)
from exceptions import (
    RecurrenceRuleNotFound,
    RecurrenceTemplateNotFound,
    TagNotFound,
    TaskScheduleOverlap,
)
from helpers import create_tag, tag_ids
from services.tasks import TaskService


async def occurrence_count(test_engine: AsyncEngine, task_id) -> int:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT count(*)
                FROM scheduled_task
                WHERE task_id = :task_id
            """),
            {"task_id": task_id},
        )
        return result.scalar_one()


async def max_generated_instance_date(test_engine: AsyncEngine, recurrence_id):
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT max(planned_date)
                FROM task_recurrence_instance
                WHERE series_id = :recurrence_id
            """),
            {"recurrence_id": recurrence_id},
        )
        return result.scalar_one()


async def generated_instance_dates(
    test_engine: AsyncEngine, recurrence_id: UUID
) -> list[tuple[int, date]]:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT sequence_no, planned_date
                FROM task_recurrence_instance
                WHERE series_id = :recurrence_id AND deleted_at IS NULL
                ORDER BY sequence_no
            """),
            {"recurrence_id": recurrence_id},
        )
        return [(row.sequence_no, row.planned_date) for row in result]


async def recurrence_template_tag_link_count(
    test_engine: AsyncEngine,
    *,
    template_id: UUID,
    tag_id: UUID,
) -> int:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT count(*)
                FROM task_recurrence_template_tag
                WHERE template_id = :template_id AND tag_id = :tag_id
            """),
            {"template_id": template_id, "tag_id": tag_id},
        )
        return result.scalar_one()


async def recurrence_task_tag_link_count(
    test_engine: AsyncEngine,
    *,
    template_id: UUID,
    tag_id: UUID,
) -> int:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT count(*)
                FROM task_tag
                JOIN task_recurrence_instance
                    ON task_recurrence_instance.task_id = task_tag.task_id
                JOIN task_recurrence_series
                    ON task_recurrence_series.series_id = task_recurrence_instance.series_id
                WHERE
                    task_recurrence_series.template_id = :template_id
                    AND task_tag.tag_id = :tag_id
            """),
            {"template_id": template_id, "tag_id": tag_id},
        )
        return result.scalar_one()


async def conflict_count(test_engine: AsyncEngine, recurrence_id) -> int:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT count(*)
                FROM task_recurrence_materialization_conflict
                WHERE series_id = :recurrence_id
            """),
            {"recurrence_id": recurrence_id},
        )
        return result.scalar_one()


async def resolved_conflict_count(test_engine: AsyncEngine, recurrence_id) -> int:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT count(*)
                FROM task_recurrence_materialization_conflict
                WHERE series_id = :recurrence_id AND resolved_at IS NOT NULL
            """),
            {"recurrence_id": recurrence_id},
        )
        return result.scalar_one()


async def delete_generated_occurrence(
    test_engine: AsyncEngine, recurrence_id, sequence_no: int
) -> None:
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("""
                DELETE FROM task_recurrence_instance
                WHERE series_id = :recurrence_id AND sequence_no = :sequence_no
                RETURNING task_id
            """),
            {"recurrence_id": recurrence_id, "sequence_no": sequence_no},
        )
        task_id = result.scalar_one()
        await conn.execute(
            text("DELETE FROM scheduled_task WHERE task_id = :task_id"),
            {"task_id": task_id},
        )
        await conn.execute(text("DELETE FROM task WHERE task_id = :task_id"), {"task_id": task_id})


def scheduled_recurrence(
    *,
    frequency: RecurrenceFrequency,
    schedule: Schedule,
    interval: int = 1,
    repeat_until: datetime | None = None,
    occurrences_limit: int | None = None,
) -> AddTaskRecurrence:
    starts_at = schedule.starts_at
    return AddTaskRecurrence(
        frequency=frequency,
        anchor_date=starts_at.date(),
        default_time=starts_at.time(),
        default_duration=schedule.ends_at - starts_at,
        interval=interval,
        weekdays=(Weekday(starts_at.isoweekday()),)
        if frequency == RecurrenceFrequency.WEEKLY
        else (),
        month_rule=(
            RecurrenceMonthRule(month_day=starts_at.day)
            if frequency == RecurrenceFrequency.MONTHLY
            else None
        ),
        repeat_until=repeat_until.date() if repeat_until is not None else None,
        occurrences_limit=occurrences_limit,
    )


async def create_task_recurrence_rule(
    task_service: TaskService,
    user_id,
    title: str,
    data: AddTaskRecurrence,
    *,
    description: str | None = None,
    priority: TaskPriority = TaskPriority.NORMAL,
):
    template = await task_service.add_task_recurrence_template(
        user_id,
        AddTaskRecurrenceTemplate(
            title=title,
            rules=(data,),
            description=description,
            priority=priority,
        ),
    )
    return template.rules[0]


async def create_recurrence_template(
    task_service: TaskService,
    *,
    title: str,
    frequency: RecurrenceFrequency = RecurrenceFrequency.DAILY,
    priority: TaskPriority = TaskPriority.NORMAL,
    tag_ids: tuple[UUID, ...] = (),
    starts_at: datetime = datetime(2099, 12, 1, 9, 0),
    user_id=TEST_USER_ID,
):
    return await task_service.add_task_recurrence_template(
        user_id,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}{title}",
            priority=priority,
            tag_ids=tag_ids,
            rules=(
                scheduled_recurrence(
                    frequency=frequency,
                    occurrences_limit=1,
                    schedule=Schedule(
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(hours=1),
                    ),
                ),
            ),
        ),
    )


async def create_materialization_conflict(
    task_service: TaskService,
    test_engine: AsyncEngine,
    *,
    starts_at: datetime,
    ends_at: datetime,
    title: str,
    user_id=TEST_USER_ID,
    priority: TaskPriority = TaskPriority.NORMAL,
    blocker_user_id=TEST_USER_ID,
):
    first_schedule = Schedule(starts_at=starts_at, ends_at=ends_at)
    conflict_schedule = Schedule(
        starts_at=starts_at + timedelta(days=1),
        ends_at=ends_at + timedelta(days=1),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        user_id,
        f"{TEST_TITLE_PREFIX}{title}",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=first_schedule,
            occurrences_limit=3,
        ),
        priority=priority,
    )
    await delete_generated_occurrence(test_engine, recurrence.recurrence_id, 2)
    blocker = await task_service.create_task(
        blocker_user_id,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}{title}-blocker",
            due_at=conflict_schedule.ends_at,
            schedule=conflict_schedule,
        ),
    )
    await task_service.materialize_recurrence_instances(
        user_id,
        (
            Schedule(
                starts_at=conflict_schedule.starts_at.replace(hour=0),
                ends_at=conflict_schedule.starts_at.replace(hour=0) + timedelta(days=1),
            ),
        ),
    )
    return recurrence, conflict_schedule, blocker


@pytest.mark.asyncio
async def test_recurrence_rule_configuration_round_trips_without_loss(
    task_service: TaskService,
) -> None:
    weekly = AddTaskRecurrence(
        frequency=RecurrenceFrequency.WEEKLY,
        anchor_date=datetime(2099, 8, 3).date(),
        default_time=datetime(2099, 8, 3, 9).time(),
        interval=2,
        weekdays=(Weekday.MONDAY, Weekday.THURSDAY),
        occurrences_limit=4,
    )
    monthly = AddTaskRecurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        anchor_date=datetime(2099, 8, 4).date(),
        default_time=datetime(2099, 8, 4, 11).time(),
        month_rule=RecurrenceMonthRule(
            week_of_month=-1,
            weekday=Weekday.FRIDAY,
        ),
        repeat_until=datetime(2100, 8, 4).date(),
    )

    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}rich-rule-round-trip",
            rules=(weekly, monthly),
        ),
    )
    rules = await task_service.get_task_recurrence_rules(
        TEST_USER_ID,
        template.template_id,
    )

    assert [rule.frequency for rule in rules] == [
        RecurrenceFrequency.WEEKLY,
        RecurrenceFrequency.MONTHLY,
    ]
    assert rules[0].weekdays == weekly.weekdays
    assert rules[1].month_rule == monthly.month_rule
    assert rules[1].repeat_until == monthly.repeat_until


@pytest.mark.asyncio
async def test_deadline_only_recurrence_materializes_tasks_without_schedules(
    task_service: TaskService,
) -> None:
    anchor = datetime(2099, 8, 10, 9, 30)
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}deadline-only-recurrence",
            rules=(
                AddTaskRecurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    anchor_date=anchor.date(),
                    default_time=anchor.time(),
                    occurrences_limit=2,
                ),
            ),
        ),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=template.title),
    )

    assert [task.due_at for task in tasks.tasks] == [anchor, anchor + timedelta(days=1)]
    assert all(task.schedule is None for task in tasks.tasks)
    assert template.rules[0].schedule is None


@pytest.mark.asyncio
async def test_recurrence_update_can_add_and_remove_future_schedules(
    task_service: TaskService,
) -> None:
    anchor = datetime(2099, 8, 20, 8, 0)
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}toggle-recurrence-duration",
            rules=(
                AddTaskRecurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    anchor_date=anchor.date(),
                    default_time=anchor.time(),
                    occurrences_limit=2,
                ),
            ),
        ),
    )
    recurrence = template.rules[0]

    scheduled_rule = await task_service.update_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        UpdateTaskRecurrence(
            anchor_date=anchor.date(),
            default_time=anchor.time(),
            default_duration=timedelta(minutes=45),
            occurrences_limit=2,
        ),
    )
    scheduled_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=template.title),
    )

    assert scheduled_rule.frequency == recurrence.frequency
    assert all(task.schedule is not None for task in scheduled_tasks.tasks)
    assert [task.due_at for task in scheduled_tasks.tasks] == [
        anchor + timedelta(minutes=45),
        anchor + timedelta(days=1, minutes=45),
    ]

    deadline_rule = await task_service.update_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        UpdateTaskRecurrence(
            anchor_date=anchor.date(),
            default_time=anchor.time(),
            default_duration=None,
            occurrences_limit=2,
        ),
    )
    deadline_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=template.title),
    )

    assert deadline_rule.default_duration is None
    assert all(task.schedule is None for task in deadline_tasks.tasks)
    assert [task.due_at for task in deadline_tasks.tasks] == [
        anchor,
        anchor + timedelta(days=1),
    ]


@pytest.mark.asyncio
async def test_weekly_recurrence_materializes_each_selected_weekday(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}weekly-calendar-generation",
        AddTaskRecurrence(
            frequency=RecurrenceFrequency.WEEKLY,
            anchor_date=datetime(2099, 8, 3).date(),
            default_time=datetime(2099, 8, 3, 9).time(),
            interval=2,
            weekdays=(Weekday.MONDAY, Weekday.THURSDAY),
            occurrences_limit=5,
        ),
    )

    assert await generated_instance_dates(test_engine, recurrence.recurrence_id) == [
        (1, datetime(2099, 8, 3).date()),
        (2, datetime(2099, 8, 6).date()),
        (3, datetime(2099, 8, 17).date()),
        (4, datetime(2099, 8, 20).date()),
        (5, datetime(2099, 8, 31).date()),
    ]


@pytest.mark.asyncio
async def test_weekly_overlap_check_uses_each_selected_weekday(
    task_service: TaskService,
) -> None:
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}weekly-overlap-calendar",
            rules=(
                AddTaskRecurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    anchor_date=datetime(2099, 8, 1).date(),
                    default_time=datetime(2099, 8, 1, 8).time(),
                    occurrences_limit=1,
                ),
            ),
        ),
    )
    await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}weekly-overlap-blocker",
            due_at=datetime(2099, 8, 6, 10),
            schedule=Schedule(
                starts_at=datetime(2099, 8, 6, 9),
                ends_at=datetime(2099, 8, 6, 10),
            ),
        ),
    )

    with pytest.raises(TaskScheduleOverlap):
        await task_service.add_task_recurrence_rule(
            TEST_USER_ID,
            template.template_id,
            AddTaskRecurrence(
                frequency=RecurrenceFrequency.WEEKLY,
                anchor_date=datetime(2099, 8, 3).date(),
                default_time=datetime(2099, 8, 3, 9).time(),
                default_duration=timedelta(hours=1),
                weekdays=(Weekday.MONDAY, Weekday.THURSDAY),
                occurrences_limit=2,
            ),
        )


@pytest.mark.asyncio
async def test_monthly_recurrence_skips_dates_absent_from_a_month(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}monthly-day-generation",
        AddTaskRecurrence(
            frequency=RecurrenceFrequency.MONTHLY,
            anchor_date=datetime(2099, 8, 31).date(),
            default_time=datetime(2099, 8, 31, 9).time(),
            month_rule=RecurrenceMonthRule(month_day=31),
            occurrences_limit=4,
        ),
    )

    assert await generated_instance_dates(test_engine, recurrence.recurrence_id) == [
        (1, datetime(2099, 8, 31).date()),
        (2, datetime(2099, 10, 31).date()),
        (3, datetime(2099, 12, 31).date()),
        (4, datetime(2100, 1, 31).date()),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("week_of_month", "expected_dates"),
    [
        (
            -1,
            [
                datetime(2099, 8, 28).date(),
                datetime(2099, 9, 25).date(),
                datetime(2099, 10, 30).date(),
            ],
        ),
        (
            5,
            [datetime(2099, 8, 31).date(), datetime(2099, 11, 30).date()],
        ),
    ],
)
async def test_monthly_ordinal_weekday_counts_only_existing_occurrences(
    task_service: TaskService,
    test_engine: AsyncEngine,
    week_of_month: int,
    expected_dates: list[date],
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}monthly-ordinal-{week_of_month}",
        AddTaskRecurrence(
            frequency=RecurrenceFrequency.MONTHLY,
            anchor_date=expected_dates[0],
            default_time=datetime(2099, 8, 1, 9).time(),
            month_rule=RecurrenceMonthRule(
                week_of_month=week_of_month,
                weekday=Weekday.MONDAY if week_of_month == 5 else Weekday.FRIDAY,
            ),
            occurrences_limit=len(expected_dates),
        ),
    )

    instances = await generated_instance_dates(test_engine, recurrence.recurrence_id)
    assert instances == list(enumerate(expected_dates, start=1))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("anchor", "policy", "expected_date"),
    [
        (
            datetime(2099, 12, 31),
            RecurrenceBusinessDayPolicy.NEXT_BUSINESS_DAY,
            datetime(2100, 2, 1).date(),
        ),
        (
            datetime(2100, 4, 1),
            RecurrenceBusinessDayPolicy.PREVIOUS_BUSINESS_DAY,
            datetime(2100, 4, 30).date(),
        ),
    ],
)
async def test_monthly_business_day_adjustment_can_cross_month_boundary(
    task_service: TaskService,
    test_engine: AsyncEngine,
    anchor: datetime,
    policy: RecurrenceBusinessDayPolicy,
    expected_date: date,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}monthly-business-day-{policy.value}",
        AddTaskRecurrence(
            frequency=RecurrenceFrequency.MONTHLY,
            anchor_date=anchor.date(),
            default_time=anchor.time(),
            month_rule=RecurrenceMonthRule(
                month_day=31 if policy == RecurrenceBusinessDayPolicy.NEXT_BUSINESS_DAY else 1,
                business_day_policy=policy,
            ),
            occurrences_limit=2,
        ),
    )

    assert await generated_instance_dates(test_engine, recurrence.recurrence_id) == [
        (1, anchor.date()),
        (2, expected_date),
    ]


@pytest.mark.asyncio
async def test_recurrence_update_preserves_completed_and_customized_instances(
    task_service: TaskService,
) -> None:
    anchor = datetime(2099, 9, 20, 9)
    title = f"{TEST_TITLE_PREFIX}safe-calendar-recalculation"
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        title,
        AddTaskRecurrence(
            frequency=RecurrenceFrequency.DAILY,
            anchor_date=anchor.date(),
            default_time=anchor.time(),
            occurrences_limit=3,
        ),
    )
    original_tasks = (
        await task_service.get_tasks(TEST_USER_ID, ListTasksFilters(search_text=title))
    ).tasks
    completed = await task_service.complete_task(TEST_USER_ID, original_tasks[0].task_id)
    customized_due_at = anchor + timedelta(days=1, hours=4)
    customized = await task_service.update_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        anchor + timedelta(days=1),
        UpdateTaskOccurrence(due_at=customized_due_at),
    )

    await task_service.update_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        UpdateTaskRecurrence(
            anchor_date=anchor.date(),
            default_time=(anchor + timedelta(hours=2)).time(),
            occurrences_limit=3,
        ),
    )
    updated_tasks = (
        await task_service.get_tasks(TEST_USER_ID, ListTasksFilters(search_text=title))
    ).tasks
    tasks_by_id = {task.task_id: task for task in updated_tasks}

    assert tasks_by_id[completed.task_id].due_at == anchor
    assert customized.task_id is not None
    assert tasks_by_id[customized.task_id].due_at == customized_due_at
    assert tasks_by_id[original_tasks[2].task_id].due_at == anchor + timedelta(days=2, hours=2)


def scheduled_start(task: Task) -> datetime:
    assert task.schedule is not None
    return task.schedule.starts_at


@pytest.mark.asyncio
async def test_missing_recurrence_template_raises_template_not_found(
    task_service: TaskService,
) -> None:
    template_id = uuid4()
    schedule = Schedule(starts_at=datetime(2099, 1, 1, 10, 0), ends_at=datetime(2099, 1, 1, 11, 0))

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.get_task_recurrence_template(TEST_USER_ID, template_id)

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.get_task_recurrence_rules(TEST_USER_ID, template_id)

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.get_task_occurrences(
            TEST_USER_ID,
            template_id,
            Schedule(starts_at=datetime(2099, 1, 1), ends_at=datetime(2099, 1, 2)),
        )

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.add_task_recurrence_rule(
            TEST_USER_ID,
            template_id,
            scheduled_recurrence(
                frequency=RecurrenceFrequency.DAILY,
                schedule=schedule,
                occurrences_limit=1,
            ),
        )

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.delete_task_recurrence_template(TEST_USER_ID, template_id)


@pytest.mark.asyncio
async def test_foreign_recurrence_template_raises_template_not_found(
    task_service: TaskService,
) -> None:
    template = await create_recurrence_template(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="foreign-template-not-found",
    )

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.get_task_recurrence_template(TEST_USER_ID, template.template_id)

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.get_task_recurrence_rules(TEST_USER_ID, template.template_id)

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.delete_task_recurrence_template(TEST_USER_ID, template.template_id)

    assert (
        await task_service.get_task_recurrence_template(TEST_OTHER_USER_ID, template.template_id)
        == template
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    (
        "update_task_recurrence",
        "stop_task_recurrence",
        "delete_task_recurrence",
        "update_task_occurrence",
        "skip_task_occurrence",
    ),
)
async def test_missing_recurrence_rule_raises_rule_not_found(
    task_service: TaskService,
    action: str,
) -> None:
    recurrence_id = uuid4()
    starts_at = datetime(2099, 1, 3, 10, 0)

    with pytest.raises(RecurrenceRuleNotFound):
        if action == "update_task_recurrence":
            await task_service.update_task_recurrence(
                TEST_USER_ID,
                recurrence_id,
                UpdateTaskRecurrence(
                    anchor_date=starts_at.date(),
                    default_time=starts_at.time(),
                    default_duration=timedelta(hours=1),
                    occurrences_limit=1,
                ),
            )
        elif action == "stop_task_recurrence":
            await task_service.stop_task_recurrence(TEST_USER_ID, recurrence_id, starts_at)
        elif action == "delete_task_recurrence":
            await task_service.delete_task_recurrence(TEST_USER_ID, recurrence_id)
        elif action == "update_task_occurrence":
            await task_service.update_task_occurrence(
                TEST_USER_ID,
                recurrence_id,
                starts_at,
                UpdateTaskOccurrence(is_cancelled=True),
            )
        else:
            await task_service.skip_task_occurrence(TEST_USER_ID, recurrence_id, starts_at)


@pytest.mark.asyncio
async def test_foreign_recurrence_rule_raises_rule_not_found(
    task_service: TaskService,
) -> None:
    template = await create_recurrence_template(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title="foreign-rule-not-found",
    )

    with pytest.raises(RecurrenceRuleNotFound):
        await task_service.stop_task_recurrence(
            TEST_USER_ID,
            template.rules[0].recurrence_id,
            datetime(2099, 12, 1, 10, 0),
        )


@pytest.mark.asyncio
async def test_user_can_list_recurrence_templates_with_rules(
    task_service: TaskService,
) -> None:
    first = await create_recurrence_template(task_service, title="template-list-first")
    second = await create_recurrence_template(
        task_service,
        title="template-list-second",
        frequency=RecurrenceFrequency.WEEKLY,
        starts_at=datetime(2099, 12, 2, 9, 0),
    )

    templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(limit=1000),
    )

    rules_by_template_id = {
        template.template_id: template.rules[0].recurrence_id for template in templates
    }

    assert set(rules_by_template_id) == {first.template_id, second.template_id}
    assert rules_by_template_id == {
        first.template_id: first.rules[0].recurrence_id,
        second.template_id: second.rules[0].recurrence_id,
    }


@pytest.mark.asyncio
async def test_user_can_count_recurrence_templates(task_service: TaskService) -> None:
    await create_recurrence_template(task_service, title="template-count-first")
    await create_recurrence_template(
        task_service,
        title="template-count-second",
        starts_at=datetime(2099, 12, 2, 9, 0),
    )

    count = await task_service.count_task_recurrence_templates(TEST_USER_ID)

    assert count == 2


@pytest.mark.asyncio
async def test_user_can_filter_recurrence_templates_by_priority(
    task_service: TaskService,
) -> None:
    await create_recurrence_template(task_service, title="template-priority-normal")
    urgent = await create_recurrence_template(
        task_service,
        title="template-priority-urgent",
        priority=TaskPriority.URGENT,
        starts_at=datetime(2099, 12, 2, 9, 0),
    )

    templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(priorities=(TaskPriority.URGENT,), limit=1000),
    )

    assert [template.template_id for template in templates] == [urgent.template_id]


@pytest.mark.asyncio
async def test_user_can_filter_recurrence_templates_by_frequency(
    task_service: TaskService,
) -> None:
    await create_recurrence_template(task_service, title="template-frequency-daily")
    weekly = await create_recurrence_template(
        task_service,
        title="template-frequency-weekly",
        frequency=RecurrenceFrequency.WEEKLY,
        starts_at=datetime(2099, 12, 2, 9, 0),
    )

    templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(frequencies=(RecurrenceFrequency.WEEKLY,), limit=1000),
    )

    assert [template.template_id for template in templates] == [weekly.template_id]


@pytest.mark.asyncio
async def test_user_can_filter_recurrence_templates_by_tag(
    task_service: TaskService,
    tag_service,
) -> None:
    first_tag = await create_tag(tag_service, name="template-filter-first")
    second_tag = await create_tag(tag_service, name="template-filter-second")
    await create_recurrence_template(
        task_service,
        title="template-tag-filter-unmatched",
        tag_ids=(second_tag.tag_id,),
    )
    tagged = await create_recurrence_template(
        task_service,
        title="template-tag-filter-matched",
        tag_ids=(first_tag.tag_id, second_tag.tag_id),
        starts_at=datetime(2099, 12, 2, 9, 0),
    )

    templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(tag_ids=(first_tag.tag_id,), limit=1000),
    )
    count = await task_service.count_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(tag_ids=(first_tag.tag_id,)),
    )

    assert [template.template_id for template in templates] == [tagged.template_id]
    assert tag_ids(templates[0].tags) == {first_tag.tag_id, second_tag.tag_id}
    assert count == 1


@pytest.mark.asyncio
async def test_user_can_count_filtered_recurrence_templates(
    task_service: TaskService,
) -> None:
    await create_recurrence_template(task_service, title="template-count-filter-daily")
    await create_recurrence_template(
        task_service,
        title="template-count-filter-weekly",
        frequency=RecurrenceFrequency.WEEKLY,
        priority=TaskPriority.URGENT,
        starts_at=datetime(2099, 12, 2, 9, 0),
    )

    count = await task_service.count_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(
            frequencies=(RecurrenceFrequency.WEEKLY,),
            priorities=(TaskPriority.URGENT,),
        ),
    )

    assert count == 1


@pytest.mark.asyncio
async def test_user_can_page_recurrence_templates(task_service: TaskService) -> None:
    first = await create_recurrence_template(task_service, title="template-page-first")
    second = await create_recurrence_template(
        task_service,
        title="template-page-second",
        starts_at=datetime(2099, 12, 2, 9, 0),
    )
    third = await create_recurrence_template(
        task_service,
        title="template-page-third",
        starts_at=datetime(2099, 12, 3, 9, 0),
    )

    all_templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(limit=1000),
    )
    paged = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(limit=2, offset=1),
    )

    assert {template.template_id for template in all_templates} == {
        first.template_id,
        second.template_id,
        third.template_id,
    }
    assert [template.template_id for template in paged] == [
        template.template_id for template in all_templates[1:3]
    ]


@pytest.mark.asyncio
async def test_user_cannot_list_other_users_recurrence_templates(
    task_service: TaskService,
) -> None:
    own = await create_recurrence_template(task_service, title="template-isolation-own")
    other = await create_recurrence_template(
        task_service,
        title="template-isolation-other",
        user_id=TEST_OTHER_USER_ID,
    )

    templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(limit=1000),
    )
    count = await task_service.count_task_recurrence_templates(TEST_USER_ID)

    assert [template.template_id for template in templates] == [own.template_id]
    assert other.template_id not in [template.template_id for template in templates]
    assert count == 1


@pytest.mark.asyncio
async def test_user_can_add_task_recurrence_and_view_occurrences(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-standup",
            due_at=datetime(2099, 9, 1, 10, 0),
        ),
    )

    # Act
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 9, 1, 10, 0),
                ends_at=datetime(2099, 9, 1, 11, 0),
            ),
            occurrences_limit=3,
        ),
    )
    occurrences = await task_service.get_task_occurrences(
        TEST_USER_ID,
        recurrence.template_id,
        Schedule(
            starts_at=datetime(2099, 9, 1, 0, 0),
            ends_at=datetime(2099, 9, 4, 0, 0),
        ),
    )

    # Assert
    assert recurrence.template_id is not None
    assert [occurrence.schedule for occurrence in occurrences] == [
        Schedule(starts_at=datetime(2099, 9, 1, 10, 0), ends_at=datetime(2099, 9, 1, 11, 0)),
        Schedule(starts_at=datetime(2099, 9, 2, 10, 0), ends_at=datetime(2099, 9, 2, 11, 0)),
        Schedule(starts_at=datetime(2099, 9, 3, 10, 0), ends_at=datetime(2099, 9, 3, 11, 0)),
    ]


@pytest.mark.asyncio
async def test_user_can_add_recurrence_template_with_multiple_rules(
    task_service: TaskService,
) -> None:
    # Arrange
    morning = scheduled_recurrence(
        frequency=RecurrenceFrequency.DAILY,
        schedule=Schedule(
            starts_at=datetime(2099, 9, 1, 8, 0),
            ends_at=datetime(2099, 9, 1, 8, 30),
        ),
        occurrences_limit=2,
    )
    evening = scheduled_recurrence(
        frequency=RecurrenceFrequency.DAILY,
        schedule=Schedule(
            starts_at=datetime(2099, 9, 1, 20, 0),
            ends_at=datetime(2099, 9, 1, 20, 30),
        ),
        occurrences_limit=2,
    )

    # Act
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-multi-rule",
            rules=(morning, evening),
        ),
    )
    rules = await task_service.get_task_recurrence_rules(TEST_USER_ID, template.template_id)
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 9, 1, 0, 0),
            ends_to=datetime(2099, 9, 3, 0, 0),
        ),
    )

    # Assert
    assert len(template.rules) == 2
    assert [rule.recurrence_id for rule in rules] == [rule.recurrence_id for rule in template.rules]
    assert [task.schedule for task in tasks.tasks] == [
        Schedule(starts_at=datetime(2099, 9, 1, 8, 0), ends_at=datetime(2099, 9, 1, 8, 30)),
        Schedule(starts_at=datetime(2099, 9, 1, 20, 0), ends_at=datetime(2099, 9, 1, 20, 30)),
        Schedule(starts_at=datetime(2099, 9, 2, 8, 0), ends_at=datetime(2099, 9, 2, 8, 30)),
        Schedule(starts_at=datetime(2099, 9, 2, 20, 0), ends_at=datetime(2099, 9, 2, 20, 30)),
    ]


@pytest.mark.asyncio
async def test_deleting_recurrence_template_preserves_completed_generated_tasks(
    task_service: TaskService,
) -> None:
    starts_at = datetime(2099, 9, 5, 8, 0)
    title = f"{TEST_TITLE_PREFIX}delete-recurrence-template"
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=title,
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(minutes=30),
                    ),
                    occurrences_limit=2,
                ),
            ),
        ),
    )
    generated_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=title),
    )
    completed_task = await task_service.complete_task(
        TEST_USER_ID,
        generated_tasks.tasks[0].task_id,
    )

    await task_service.delete_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
    )

    with pytest.raises(RecurrenceTemplateNotFound):
        await task_service.get_task_recurrence_template(TEST_USER_ID, template.template_id)

    templates = await task_service.get_task_recurrence_templates(TEST_USER_ID)
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=title),
    )
    assert all(item.template_id != template.template_id for item in templates)
    assert [task.task_id for task in tasks.tasks] == [completed_task.task_id]
    assert tasks.tasks[0].status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_recurrence_template_tags_are_copied_to_materialized_tasks(
    task_service: TaskService,
    tag_service,
) -> None:
    # Arrange
    tag = await create_tag(tag_service, name="recurrence-template")
    other_tag = await create_tag(tag_service, name="recurrence-template-other")
    starts_at = datetime(2099, 9, 10, 10, 0)

    # Act
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-tagged-template",
            tag_ids=(tag.tag_id,),
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=2,
                ),
            ),
        ),
    )
    fetched_template = await task_service.get_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
    )
    tagged_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=2),
            tag_ids=(tag.tag_id,),
        ),
    )
    other_tag_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=2),
            tag_ids=(other_tag.tag_id,),
        ),
    )

    # Assert
    assert tag_ids(template.tags) == {tag.tag_id}
    assert tag_ids(fetched_template.tags) == {tag.tag_id}
    assert len(tagged_tasks.tasks) == 2
    assert all(tag_ids(task.tags) == {tag.tag_id} for task in tagged_tasks.tasks)
    assert other_tag_tasks.tasks == []


@pytest.mark.asyncio
async def test_recurrence_template_tags_are_returned_in_template_list(
    task_service: TaskService,
    tag_service,
) -> None:
    # Arrange
    first_tag = await create_tag(tag_service, name="recurrence-template-list-first")
    second_tag = await create_tag(tag_service, name="recurrence-template-list-second")
    starts_at = datetime(2099, 9, 20, 10, 0)

    # Act
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-tagged-list-template",
            tag_ids=(first_tag.tag_id, second_tag.tag_id, first_tag.tag_id),
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=1,
                ),
            ),
        ),
    )
    templates = await task_service.get_task_recurrence_templates(
        TEST_USER_ID,
        ListTaskRecurrenceTemplatesFilters(limit=1000),
    )

    # Assert
    tagged_template = next(item for item in templates if item.template_id == template.template_id)
    assert tag_ids(tagged_template.tags) == {first_tag.tag_id, second_tag.tag_id}
    assert len(tagged_template.rules) == 1


@pytest.mark.asyncio
async def test_recurrence_template_rejects_tag_from_another_user(
    task_service: TaskService,
    tag_service,
) -> None:
    # Arrange
    other_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name="recurrence-template-other-user",
    )
    starts_at = datetime(2099, 9, 25, 10, 0)

    # Act, Assert
    with pytest.raises(TagNotFound):
        await task_service.add_task_recurrence_template(
            TEST_USER_ID,
            AddTaskRecurrenceTemplate(
                title=f"{TEST_TITLE_PREFIX}recurring-invalid-tag-template",
                tag_ids=(other_tag.tag_id,),
                rules=(
                    scheduled_recurrence(
                        frequency=RecurrenceFrequency.DAILY,
                        schedule=Schedule(
                            starts_at=starts_at,
                            ends_at=starts_at + timedelta(hours=1),
                        ),
                        occurrences_limit=1,
                    ),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_user_can_add_tag_to_recurrence_template_and_current_active_instances(
    task_service: TaskService,
    tag_service,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-add-later")
    now = datetime.now().replace(microsecond=0)
    starts_at = now - timedelta(days=1, hours=1)
    title = f"{TEST_TITLE_PREFIX}recurring-add-tag-later"
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=title,
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=2)),
                    occurrences_limit=4,
                ),
            ),
        ),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=4),
            limit=1000,
        ),
    )
    past, current, completed_future, active_future = sorted(tasks.tasks, key=scheduled_start)
    await task_service.complete_task(TEST_USER_ID, completed_future.task_id)

    updated_template = await task_service.add_tag_to_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )
    tagged_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=4),
            tag_ids=(tag.tag_id,),
            limit=1000,
        ),
    )
    past = await task_service.get_task(TEST_USER_ID, past.task_id)
    completed_future = await task_service.get_task(TEST_USER_ID, completed_future.task_id)
    history = await task_service.get_task_recurrence_template_history(
        TEST_USER_ID, template.template_id
    )

    assert tag_ids(updated_template.tags) == {tag.tag_id}
    assert {task.task_id for task in tagged_tasks.tasks} == {
        current.task_id,
        active_future.task_id,
    }
    assert tag_ids(past.tags) == set()
    assert tag_ids(completed_future.tags) == set()
    assert history[-1].event_type == AuditEventType.TASK_RECURRENCE_TEMPLATE_TAG_ADDED
    assert history[-1].data == {"tag_id": str(tag.tag_id)}


@pytest.mark.asyncio
async def test_user_can_delete_tag_from_recurrence_template_and_current_active_instances(
    task_service: TaskService,
    tag_service,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-remove-later")
    now = datetime.now().replace(microsecond=0)
    starts_at = now - timedelta(days=1, hours=1)
    title = f"{TEST_TITLE_PREFIX}recurring-remove-tag-later"
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=title,
            tag_ids=(tag.tag_id,),
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=2)),
                    occurrences_limit=4,
                ),
            ),
        ),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=4),
            limit=1000,
        ),
    )
    past, current, completed_future, active_future = sorted(tasks.tasks, key=scheduled_start)
    await task_service.complete_task(TEST_USER_ID, completed_future.task_id)

    updated_template = await task_service.delete_tag_from_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )
    tagged_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=4),
            tag_ids=(tag.tag_id,),
            limit=1000,
        ),
    )
    current = await task_service.get_task(TEST_USER_ID, current.task_id)
    completed_future = await task_service.get_task(TEST_USER_ID, completed_future.task_id)
    active_future = await task_service.get_task(TEST_USER_ID, active_future.task_id)
    history = await task_service.get_task_recurrence_template_history(
        TEST_USER_ID, template.template_id
    )

    assert tag_ids(updated_template.tags) == set()
    assert {task.task_id for task in tagged_tasks.tasks} == {
        past.task_id,
        completed_future.task_id,
    }
    assert tag_ids(current.tags) == set()
    assert tag_ids(completed_future.tags) == {tag.tag_id}
    assert tag_ids(active_future.tags) == set()
    assert history[-1].event_type == AuditEventType.TASK_RECURRENCE_TEMPLATE_TAG_REMOVED
    assert history[-1].data == {"tag_id": str(tag.tag_id)}


@pytest.mark.asyncio
async def test_adding_tag_to_recurrence_template_is_idempotent(
    task_service: TaskService,
    tag_service,
    test_engine: AsyncEngine,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-add-idempotent")
    starts_at = datetime(2099, 11, 1, 10, 0)
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-add-tag-idempotent",
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=2,
                ),
            ),
        ),
    )

    first = await task_service.add_tag_to_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )
    second = await task_service.add_tag_to_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )

    assert tag_ids(first.tags) == {tag.tag_id}
    assert tag_ids(second.tags) == {tag.tag_id}
    assert (
        await recurrence_template_tag_link_count(
            test_engine,
            template_id=template.template_id,
            tag_id=tag.tag_id,
        )
        == 1
    )
    assert (
        await recurrence_task_tag_link_count(
            test_engine,
            template_id=template.template_id,
            tag_id=tag.tag_id,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_deleting_tag_from_recurrence_template_is_idempotent(
    task_service: TaskService,
    tag_service,
    test_engine: AsyncEngine,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-delete-idempotent")
    starts_at = datetime(2099, 11, 5, 10, 0)
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-delete-tag-idempotent",
            tag_ids=(tag.tag_id,),
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=2,
                ),
            ),
        ),
    )

    first = await task_service.delete_tag_from_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )
    second = await task_service.delete_tag_from_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )

    assert tag_ids(first.tags) == set()
    assert tag_ids(second.tags) == set()
    assert (
        await recurrence_template_tag_link_count(
            test_engine,
            template_id=template.template_id,
            tag_id=tag.tag_id,
        )
        == 0
    )
    assert (
        await recurrence_task_tag_link_count(
            test_engine,
            template_id=template.template_id,
            tag_id=tag.tag_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_future_recurrence_materialization_uses_added_template_tag(
    task_service: TaskService,
    tag_service,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-future-added")
    starts_at = datetime(2099, 1, 1, 10, 0)
    future_window = Schedule(
        starts_at=starts_at + timedelta(days=95),
        ends_at=starts_at + timedelta(days=97),
    )
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-future-added-tag",
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=100,
                ),
            ),
        ),
    )
    await task_service.add_tag_to_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )

    await task_service.materialize_recurrence_instances(TEST_USER_ID, (future_window,))
    tagged_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=future_window.starts_at,
            ends_to=future_window.ends_at,
            tag_ids=(tag.tag_id,),
            limit=1000,
        ),
    )

    assert len(tagged_tasks.tasks) == 2
    assert all(tag_ids(task.tags) == {tag.tag_id} for task in tagged_tasks.tasks)


@pytest.mark.asyncio
async def test_future_recurrence_materialization_uses_removed_template_tag(
    task_service: TaskService,
    tag_service,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-future-removed")
    starts_at = datetime(2099, 1, 10, 10, 0)
    future_window = Schedule(
        starts_at=starts_at + timedelta(days=95),
        ends_at=starts_at + timedelta(days=97),
    )
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-future-removed-tag",
            tag_ids=(tag.tag_id,),
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=100,
                ),
            ),
        ),
    )
    await task_service.delete_tag_from_task_recurrence_template(
        TEST_USER_ID,
        template.template_id,
        tag.tag_id,
    )

    await task_service.materialize_recurrence_instances(TEST_USER_ID, (future_window,))
    future_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=future_window.starts_at,
            ends_to=future_window.ends_at,
            limit=1000,
        ),
    )
    tagged_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=future_window.starts_at,
            ends_to=future_window.ends_at,
            tag_ids=(tag.tag_id,),
            limit=1000,
        ),
    )

    assert len(future_tasks.tasks) == 2
    assert all(tag_ids(task.tags) == set() for task in future_tasks.tasks)
    assert tagged_tasks.tasks == []


@pytest.mark.asyncio
async def test_future_recurrence_materialization_ignores_soft_deleted_template_tag(
    task_service: TaskService,
    tag_service,
    test_engine: AsyncEngine,
) -> None:
    tag = await create_tag(tag_service, name="recurrence-template-soft-deleted")
    starts_at = datetime(2099, 1, 20, 10, 0)
    future_window = Schedule(
        starts_at=starts_at + timedelta(days=95),
        ends_at=starts_at + timedelta(days=97),
    )
    template = await task_service.add_task_recurrence_template(
        TEST_USER_ID,
        AddTaskRecurrenceTemplate(
            title=f"{TEST_TITLE_PREFIX}recurring-soft-deleted-tag",
            tag_ids=(tag.tag_id,),
            rules=(
                scheduled_recurrence(
                    frequency=RecurrenceFrequency.DAILY,
                    schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
                    occurrences_limit=100,
                ),
            ),
        ),
    )
    async with test_engine.begin() as connection:
        await connection.execute(
            text("UPDATE tag SET deleted_at = now() WHERE tag_id = :tag_id"),
            {"tag_id": tag.tag_id},
        )

    await task_service.materialize_recurrence_instances(TEST_USER_ID, (future_window,))
    future_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=future_window.starts_at,
            ends_to=future_window.ends_at,
            limit=1000,
        ),
    )

    assert (
        await recurrence_template_tag_link_count(
            test_engine,
            template_id=template.template_id,
            tag_id=tag.tag_id,
        )
        == 1
    )
    assert len(future_tasks.tasks) == 2
    assert all(tag_ids(task.tags) == set() for task in future_tasks.tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    (
        "add_tag_to_task_recurrence_template",
        "delete_tag_from_task_recurrence_template",
    ),
)
async def test_user_cannot_change_tags_on_another_users_recurrence_template(
    task_service: TaskService,
    tag_service,
    action: str,
) -> None:
    tag = await create_tag(tag_service, name=f"{action}-own-tag")
    other_template = await create_recurrence_template(
        task_service,
        user_id=TEST_OTHER_USER_ID,
        title=f"{action}-other-template",
    )

    with pytest.raises(RecurrenceTemplateNotFound):
        await getattr(task_service, action)(TEST_USER_ID, other_template.template_id, tag.tag_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    (
        "add_tag_to_task_recurrence_template",
        "delete_tag_from_task_recurrence_template",
    ),
)
async def test_user_cannot_use_another_users_tag_for_recurrence_template(
    task_service: TaskService,
    tag_service,
    action: str,
) -> None:
    template = await create_recurrence_template(
        task_service,
        title=f"{action}-own-template",
    )
    other_tag = await create_tag(
        tag_service,
        user_id=TEST_OTHER_USER_ID,
        name=f"{action}-other-tag",
    )

    with pytest.raises(TagNotFound):
        await getattr(task_service, action)(TEST_USER_ID, template.template_id, other_tag.tag_id)


@pytest.mark.asyncio
async def test_scheduled_task_occurrence_is_created_for_single_schedule(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    schedule = Schedule(
        starts_at=datetime(2099, 10, 1, 10, 0),
        ends_at=datetime(2099, 10, 1, 11, 0),
    )

    # Act
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}single-occurrence-create",
            due_at=schedule.ends_at,
            schedule=schedule,
        ),
    )

    # Assert
    assert await occurrence_count(test_engine, task.task_id) == 1
    task_list = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(starts_from=schedule.starts_at, ends_to=schedule.ends_at),
    )
    assert task_list.tasks == [task]


@pytest.mark.asyncio
async def test_scheduled_task_occurrence_is_updated_for_single_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    old_schedule = Schedule(
        starts_at=datetime(2099, 10, 2, 10, 0),
        ends_at=datetime(2099, 10, 2, 11, 0),
    )
    new_schedule = Schedule(
        starts_at=datetime(2099, 10, 2, 14, 0),
        ends_at=datetime(2099, 10, 2, 15, 0),
    )
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}single-occurrence-update",
            due_at=old_schedule.ends_at,
            schedule=old_schedule,
        ),
    )

    # Act
    await task_service.update_task(
        TEST_USER_ID,
        task.task_id,
        UpdateTaskData(schedule=new_schedule),
    )
    old_window = await task_service.get_free_time(TEST_USER_ID, [old_schedule])
    new_window_availability = await task_service.check_schedule_availability(
        TEST_USER_ID, new_schedule
    )

    # Assert
    assert old_window == [FreeTime(starts_at=old_schedule.starts_at, ends_at=old_schedule.ends_at)]
    assert not new_window_availability.can_add_task


@pytest.mark.asyncio
async def test_scheduled_task_occurrence_is_deleted_with_single_schedule(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    # Arrange
    schedule = Schedule(
        starts_at=datetime(2099, 10, 3, 10, 0),
        ends_at=datetime(2099, 10, 3, 11, 0),
    )
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}single-occurrence-delete",
            due_at=schedule.ends_at,
            schedule=schedule,
        ),
    )

    # Act
    await task_service.delete_schedule_from_task(TEST_USER_ID, task.task_id)

    # Assert
    assert await occurrence_count(test_engine, task.task_id) == 0
    assert await task_service.get_free_time(TEST_USER_ID, [schedule]) == [
        FreeTime(starts_at=schedule.starts_at, ends_at=schedule.ends_at)
    ]


@pytest.mark.asyncio
async def test_free_time_accounts_for_recurring_task_occurrences(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-focus",
            due_at=datetime(2099, 9, 5, 10, 0),
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 9, 5, 10, 0),
                ends_at=datetime(2099, 9, 5, 11, 0),
            ),
            occurrences_limit=2,
        ),
    )

    # Act
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        [
            Schedule(starts_at=datetime(2099, 9, 5, 9, 0), ends_at=datetime(2099, 9, 5, 12, 0)),
            Schedule(starts_at=datetime(2099, 9, 6, 9, 0), ends_at=datetime(2099, 9, 6, 12, 0)),
        ],
    )

    # Assert
    assert sut == [
        FreeTime(starts_at=datetime(2099, 9, 5, 9, 0), ends_at=datetime(2099, 9, 5, 10, 0)),
        FreeTime(starts_at=datetime(2099, 9, 5, 11, 0), ends_at=datetime(2099, 9, 5, 12, 0)),
        FreeTime(starts_at=datetime(2099, 9, 6, 9, 0), ends_at=datetime(2099, 9, 6, 10, 0)),
        FreeTime(starts_at=datetime(2099, 9, 6, 11, 0), ends_at=datetime(2099, 9, 6, 12, 0)),
    ]


@pytest.mark.asyncio
async def test_schedule_availability_accounts_for_recurring_task_occurrence(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-availability",
            due_at=datetime(2099, 10, 4, 10, 0),
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 10, 4, 10, 0),
                ends_at=datetime(2099, 10, 4, 11, 0),
            ),
            occurrences_limit=1,
        ),
    )

    # Act
    sut = await task_service.check_schedule_availability(
        TEST_USER_ID,
        Schedule(starts_at=datetime(2099, 10, 4, 10, 30), ends_at=datetime(2099, 10, 4, 11, 30)),
    )

    # Assert
    assert not sut.can_add_task
    assert [blocking.title for blocking in sut.blocking_tasks] == [task.title]


@pytest.mark.asyncio
async def test_task_list_and_count_include_recurring_occurrences(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-list",
            due_at=datetime(2099, 9, 20, 10, 0),
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 9, 20, 10, 0),
                ends_at=datetime(2099, 9, 20, 11, 0),
            ),
            occurrences_limit=2,
        ),
    )
    filters = ListTasksFilters(
        starts_from=datetime(2099, 9, 20, 0, 0),
        ends_to=datetime(2099, 9, 22, 0, 0),
    )

    # Act
    tasks = await task_service.get_tasks(TEST_USER_ID, filters)
    count = await task_service.count_tasks(TEST_USER_ID, filters)
    tasks_without_recurring = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=filters.starts_from,
            ends_to=filters.ends_to,
            include_recurring=False,
        ),
    )
    count_without_recurring = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=filters.starts_from,
            ends_to=filters.ends_to,
            include_recurring=False,
        ),
    )

    # Assert
    assert [item.schedule for item in tasks.tasks] == [
        Schedule(starts_at=datetime(2099, 9, 20, 10, 0), ends_at=datetime(2099, 9, 20, 11, 0)),
        Schedule(starts_at=datetime(2099, 9, 21, 10, 0), ends_at=datetime(2099, 9, 21, 11, 0)),
    ]
    assert count == 2
    assert tasks_without_recurring.tasks == []
    assert count_without_recurring == 0


@pytest.mark.asyncio
async def test_task_list_filters_recurring_occurrences_by_task_fields(
    task_service: TaskService,
) -> None:
    # Arrange
    matching = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-filter-match",
            due_at=datetime(2099, 10, 5, 10, 0),
            description="recurring filter needle",
            status=TaskStatus.ACTIVE,
            priority=TaskPriority.HIGH,
        ),
    )
    non_matching = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-filter-other",
            due_at=datetime(2099, 10, 5, 10, 0),
            status=TaskStatus.CANCELLED,
            priority=TaskPriority.LOW,
        ),
    )
    for task, starts_at in (
        (matching, datetime(2099, 10, 5, 10, 0)),
        (non_matching, datetime(2099, 10, 5, 12, 0)),
    ):
        await create_task_recurrence_rule(
            task_service,
            TEST_USER_ID,
            task.title,
            scheduled_recurrence(
                frequency=RecurrenceFrequency.DAILY,
                schedule=Schedule(
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(hours=1),
                ),
                occurrences_limit=1,
            ),
            description=task.description,
            priority=task.priority,
        )

    filters = ListTasksFilters(
        starts_from=datetime(2099, 10, 5, 0, 0),
        ends_to=datetime(2099, 10, 6, 0, 0),
        statuses=(TaskStatus.ACTIVE,),
        priorities=(TaskPriority.HIGH,),
        search_text="needle",
    )

    # Act
    tasks = await task_service.get_tasks(TEST_USER_ID, filters)
    count = await task_service.count_tasks(TEST_USER_ID, filters)

    # Assert
    assert [task.title for task in tasks.tasks] == [matching.title]
    assert count == 1


@pytest.mark.asyncio
async def test_nearest_free_schedule_accounts_for_recurring_task_occurrences(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-nearest",
            due_at=datetime(2099, 9, 8, 10, 0),
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 9, 8, 10, 0),
                ends_at=datetime(2099, 9, 8, 11, 0),
            ),
            occurrences_limit=1,
        ),
    )

    # Act
    sut = await task_service.find_nearest_free_schedule(
        TEST_USER_ID,
        duration=datetime(2099, 9, 8, 10, 30) - datetime(2099, 9, 8, 10, 0),
        search_from=datetime(2099, 9, 8, 10, 0),
    )

    # Assert
    assert sut == Schedule(
        starts_at=datetime(2099, 9, 8, 11, 0),
        ends_at=datetime(2099, 9, 8, 11, 30),
    )


@pytest.mark.asyncio
async def test_user_can_reschedule_single_recurring_occurrence(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-review",
            due_at=datetime(2099, 9, 10, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 9, 10, 10, 0),
                ends_at=datetime(2099, 9, 10, 11, 0),
            ),
            occurrences_limit=2,
        ),
    )

    # Act
    await task_service.update_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 9, 11, 10, 0),
        UpdateTaskOccurrence(
            schedule=Schedule(
                starts_at=datetime(2099, 9, 11, 14, 0),
                ends_at=datetime(2099, 9, 11, 15, 0),
            ),
        ),
    )
    morning_free_time = await task_service.get_free_time(
        TEST_USER_ID,
        [Schedule(starts_at=datetime(2099, 9, 11, 9, 0), ends_at=datetime(2099, 9, 11, 12, 0))],
    )
    afternoon_availability = await task_service.check_schedule_availability(
        TEST_USER_ID,
        Schedule(starts_at=datetime(2099, 9, 11, 14, 30), ends_at=datetime(2099, 9, 11, 15, 0)),
    )

    # Assert
    assert morning_free_time == [
        FreeTime(starts_at=datetime(2099, 9, 11, 9, 0), ends_at=datetime(2099, 9, 11, 12, 0))
    ]
    assert not afternoon_availability.can_add_task
    assert [blocking.title for blocking in afternoon_availability.blocking_tasks] == [task.title]


@pytest.mark.asyncio
async def test_rescheduled_occurrence_is_listed_in_new_window_only(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-list-rescheduled",
            due_at=datetime(2099, 10, 7, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 10, 7, 10, 0),
                ends_at=datetime(2099, 10, 7, 11, 0),
            ),
            occurrences_limit=1,
        ),
    )
    new_schedule = Schedule(
        starts_at=datetime(2099, 10, 7, 14, 0),
        ends_at=datetime(2099, 10, 7, 15, 0),
    )

    # Act
    await task_service.update_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 10, 7, 10, 0),
        UpdateTaskOccurrence(schedule=new_schedule),
    )
    old_window_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 10, 7, 10, 0),
            ends_to=datetime(2099, 10, 7, 11, 0),
        ),
    )
    new_window_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=new_schedule.starts_at,
            ends_to=new_schedule.ends_at,
        ),
    )

    # Assert
    assert old_window_tasks.tasks == []
    assert [item.schedule for item in new_window_tasks.tasks] == [new_schedule]


@pytest.mark.asyncio
async def test_user_can_cancel_single_recurring_occurrence(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-cancel",
            due_at=datetime(2099, 9, 15, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 9, 15, 10, 0),
                ends_at=datetime(2099, 9, 15, 11, 0),
            ),
            occurrences_limit=2,
        ),
    )

    # Act
    await task_service.update_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 9, 15, 10, 0),
        UpdateTaskOccurrence(is_cancelled=True),
    )
    sut = await task_service.get_free_time(
        TEST_USER_ID,
        [Schedule(starts_at=datetime(2099, 9, 15, 9, 0), ends_at=datetime(2099, 9, 15, 12, 0))],
    )

    # Assert
    assert sut == [
        FreeTime(starts_at=datetime(2099, 9, 15, 9, 0), ends_at=datetime(2099, 9, 15, 12, 0))
    ]


@pytest.mark.asyncio
async def test_cancelled_recurring_occurrence_is_not_listed_as_scheduled_task(
    task_service: TaskService,
) -> None:
    # Arrange
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-cancel-list",
            due_at=datetime(2099, 10, 8, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 10, 8, 10, 0),
                ends_at=datetime(2099, 10, 8, 11, 0),
            ),
            occurrences_limit=1,
        ),
    )

    # Act
    await task_service.update_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 10, 8, 10, 0),
        UpdateTaskOccurrence(is_cancelled=True),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 10, 8, 10, 0),
            ends_to=datetime(2099, 10, 8, 11, 0),
        ),
    )
    count = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 10, 8, 10, 0),
            ends_to=datetime(2099, 10, 8, 11, 0),
        ),
    )

    # Assert
    assert tasks.tasks == []
    assert count == 0


@pytest.mark.asyncio
async def test_user_cannot_create_recurrence_overlapping_single_schedule(
    task_service: TaskService,
) -> None:
    # Arrange
    await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}single-blocks-recurrence",
            due_at=datetime(2099, 10, 9, 11, 0),
            schedule=Schedule(
                starts_at=datetime(2099, 10, 9, 10, 0),
                ends_at=datetime(2099, 10, 9, 11, 0),
            ),
        ),
    )
    recurring_task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurrence-overlaps-single",
            due_at=datetime(2099, 10, 9, 10, 30),
        ),
    )

    # Act / Assert
    with pytest.raises(TaskScheduleOverlap):
        await create_task_recurrence_rule(
            task_service,
            TEST_USER_ID,
            recurring_task.title,
            scheduled_recurrence(
                frequency=RecurrenceFrequency.DAILY,
                schedule=Schedule(
                    starts_at=datetime(2099, 10, 9, 10, 30),
                    ends_at=datetime(2099, 10, 9, 11, 30),
                ),
                occurrences_limit=1,
            ),
        )


@pytest.mark.asyncio
async def test_user_cannot_create_rule_with_overlapping_occurrences(
    task_service: TaskService,
) -> None:
    with pytest.raises(TaskScheduleOverlap):
        await create_task_recurrence_rule(
            task_service,
            TEST_USER_ID,
            f"{TEST_TITLE_PREFIX}self-overlapping-recurrence",
            AddTaskRecurrence(
                frequency=RecurrenceFrequency.DAILY,
                anchor_date=datetime(2099, 10, 9).date(),
                default_time=datetime(2099, 10, 9, 10).time(),
                default_duration=timedelta(hours=25),
                occurrences_limit=2,
            ),
        )


@pytest.mark.asyncio
async def test_user_cannot_create_recurrence_overlapping_another_recurrence(
    task_service: TaskService,
) -> None:
    # Arrange
    first = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}first-recurrence-conflict",
            due_at=datetime(2099, 10, 10, 10, 0),
        ),
    )
    second = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}second-recurrence-conflict",
            due_at=datetime(2099, 10, 10, 10, 30),
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        first.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 10, 10, 10, 0),
                ends_at=datetime(2099, 10, 10, 11, 0),
            ),
            occurrences_limit=1,
        ),
    )

    # Act / Assert
    with pytest.raises(TaskScheduleOverlap):
        await create_task_recurrence_rule(
            task_service,
            TEST_USER_ID,
            second.title,
            scheduled_recurrence(
                frequency=RecurrenceFrequency.DAILY,
                schedule=Schedule(
                    starts_at=datetime(2099, 10, 10, 10, 30),
                    ends_at=datetime(2099, 10, 10, 11, 30),
                ),
                occurrences_limit=1,
            ),
        )


@pytest.mark.asyncio
async def test_deleted_recurrence_rule_preserves_only_completed_instances(
    task_service: TaskService,
) -> None:
    # Arrange
    schedule = Schedule(
        starts_at=datetime(2099, 10, 11, 10, 0),
        ends_at=datetime(2099, 10, 11, 11, 0),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}deleted-recurring",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=schedule,
            occurrences_limit=2,
        ),
    )
    generated_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=f"{TEST_TITLE_PREFIX}deleted-recurring"),
    )
    completed_task = await task_service.complete_task(
        TEST_USER_ID,
        generated_tasks.tasks[0].task_id,
    )
    unfinished_schedule = Schedule(
        starts_at=schedule.starts_at + timedelta(days=1),
        ends_at=schedule.ends_at + timedelta(days=1),
    )

    # Act
    await task_service.delete_task_recurrence(TEST_USER_ID, recurrence.recurrence_id)
    free_time = await task_service.get_free_time(TEST_USER_ID, [unfinished_schedule])
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(search_text=f"{TEST_TITLE_PREFIX}deleted-recurring"),
    )

    # Assert
    assert free_time == [
        FreeTime(
            starts_at=unfinished_schedule.starts_at,
            ends_at=unfinished_schedule.ends_at,
        )
    ]
    assert [task.task_id for task in tasks.tasks] == [completed_task.task_id]
    assert tasks.tasks[0].status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_recurring_occurrences_are_isolated_between_users(
    task_service: TaskService,
) -> None:
    # Arrange
    schedule = Schedule(
        starts_at=datetime(2099, 10, 12, 10, 0),
        ends_at=datetime(2099, 10, 12, 11, 0),
    )
    other_task = await task_service.create_task(
        TEST_OTHER_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}foreign-recurring",
            due_at=schedule.ends_at,
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_OTHER_USER_ID,
        other_task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=schedule,
            occurrences_limit=1,
        ),
    )

    # Act
    free_time = await task_service.get_free_time(TEST_USER_ID, [schedule])
    availability = await task_service.check_schedule_availability(TEST_USER_ID, schedule)
    nearest = await task_service.find_nearest_free_schedule(
        TEST_USER_ID,
        duration=timedelta(minutes=30),
        search_from=schedule.starts_at,
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(starts_from=schedule.starts_at, ends_to=schedule.ends_at),
    )
    count = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(starts_from=schedule.starts_at, ends_to=schedule.ends_at),
    )

    # Assert
    assert free_time == [FreeTime(starts_at=schedule.starts_at, ends_at=schedule.ends_at)]
    assert availability.can_add_task
    assert availability.blocking_tasks == []
    assert nearest == Schedule(
        starts_at=schedule.starts_at,
        ends_at=schedule.starts_at + timedelta(minutes=30),
    )
    assert tasks.tasks == []
    assert count == 0


@pytest.mark.asyncio
async def test_daily_recurrence_materialization_is_capped_at_90_days(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-daily-cap",
            due_at=datetime(2099, 1, 1, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )

    await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 1, 1, 0, 0),
            ends_to=datetime(2099, 12, 31, 23, 59),
        ),
    )

    assert (
        await max_generated_instance_date(test_engine, recurrence.recurrence_id)
        <= datetime(2099, 4, 1).date()
    )


@pytest.mark.asyncio
async def test_monthly_recurrence_materialization_is_capped_at_one_year(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-monthly-cap",
            due_at=datetime(2099, 1, 1, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.MONTHLY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )

    await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 1, 1, 0, 0),
            ends_to=datetime(2101, 1, 1, 0, 0),
        ),
    )

    assert (
        await max_generated_instance_date(test_engine, recurrence.recurrence_id)
        <= datetime(2100, 1, 1).date()
    )


@pytest.mark.asyncio
async def test_materialize_recurrence_instances_for_all_owners_uses_only_owners_requiring_tail(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    requiring_recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-owner-needs-tail",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )
    await create_task_recurrence_rule(
        task_service,
        TEST_OTHER_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-owner-finished-by-count",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 15, 0),
                ends_at=datetime(2099, 1, 1, 16, 0),
            ),
            occurrences_limit=1,
        ),
    )

    owner_count = await task_service.materialize_recurrence_instances_for_all_owners(
        Schedule(starts_at=datetime(2099, 4, 15, 0, 0), ends_at=datetime(2099, 4, 16, 0, 0))
    )

    assert owner_count == 1
    assert (
        await max_generated_instance_date(test_engine, requiring_recurrence.recurrence_id)
        >= datetime(2099, 4, 15).date()
    )


@pytest.mark.asyncio
async def test_materialize_recurrence_instances_for_all_owners_skips_not_due_series(
    task_service: TaskService,
) -> None:
    await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-owner-not-due",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )

    owner_count = await task_service.materialize_recurrence_instances_for_all_owners(
        Schedule(starts_at=datetime(2099, 1, 5, 0, 0), ends_at=datetime(2099, 1, 6, 0, 0))
    )

    assert owner_count == 0


@pytest.mark.asyncio
async def test_materialize_recurrence_instances_for_all_owners_skips_deleted_recurrence(
    task_service: TaskService,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-owner-deleted",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )

    await task_service.delete_task_recurrence(TEST_USER_ID, recurrence.recurrence_id)
    owner_count = await task_service.materialize_recurrence_instances_for_all_owners(
        Schedule(starts_at=datetime(2099, 4, 15, 0, 0), ends_at=datetime(2099, 4, 16, 0, 0))
    )

    assert owner_count == 0


@pytest.mark.asyncio
async def test_materialize_recurrence_instances_for_all_owners_skips_finished_generation(
    task_service: TaskService,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-owner-stopped",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )

    await task_service.stop_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 2, 1, 10, 0),
    )
    owner_count = await task_service.materialize_recurrence_instances_for_all_owners(
        Schedule(starts_at=datetime(2099, 4, 15, 0, 0), ends_at=datetime(2099, 4, 16, 0, 0))
    )

    assert owner_count == 0


@pytest.mark.asyncio
async def test_materialization_conflicts_are_returned_with_due_filtered_tasks(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-conflict",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
            occurrences_limit=3,
        ),
        priority=TaskPriority.HIGH,
    )
    conflict_schedule = Schedule(
        starts_at=datetime(2099, 1, 2, 10, 0),
        ends_at=datetime(2099, 1, 2, 11, 0),
    )
    await delete_generated_occurrence(test_engine, recurrence.recurrence_id, 2)
    blocker = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-conflict-blocker",
            due_at=conflict_schedule.ends_at,
            schedule=conflict_schedule,
        ),
    )

    await task_service.materialize_recurrence_instances(
        TEST_USER_ID,
        (Schedule(starts_at=datetime(2099, 1, 2, 0, 0), ends_at=datetime(2099, 1, 3, 0, 0)),),
    )
    without_due_filter = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=conflict_schedule.starts_at,
            ends_to=conflict_schedule.ends_at,
        ),
    )
    with_due_filter = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 1, 2, 0, 0),
            due_to=datetime(2099, 1, 2, 23, 59),
        ),
    )

    assert without_due_filter.conflicts == []
    assert [task.task_id for task in with_due_filter.tasks] == [blocker.task_id]
    assert len(with_due_filter.conflicts) == 1
    conflict = with_due_filter.conflicts[0]
    assert conflict.kind == TaskKind.RECURRENCE_CONFLICT
    assert conflict.recurrence_id == recurrence.recurrence_id
    assert conflict.schedule == conflict_schedule
    assert conflict.priority == TaskPriority.HIGH


@pytest.mark.asyncio
async def test_materialization_conflict_is_resolved_after_slot_is_freed(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence, conflict_schedule, blocker = await create_materialization_conflict(
        task_service,
        test_engine,
        starts_at=datetime(2099, 2, 1, 10, 0),
        ends_at=datetime(2099, 2, 1, 11, 0),
        title="recurring-conflict-resolve",
    )

    await task_service.delete_schedule_from_task(TEST_USER_ID, blocker.task_id)
    await task_service.materialize_recurrence_instances(
        TEST_USER_ID,
        (Schedule(starts_at=datetime(2099, 2, 2, 0, 0), ends_at=datetime(2099, 2, 3, 0, 0)),),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 2, 2, 0, 0),
            due_to=datetime(2099, 2, 2, 23, 59),
        ),
    )

    assert tasks.conflicts == []
    assert conflict_schedule in [task.schedule for task in tasks.tasks]
    assert await conflict_count(test_engine, recurrence.recurrence_id) == 1
    assert await resolved_conflict_count(test_engine, recurrence.recurrence_id) == 1


@pytest.mark.asyncio
async def test_repeated_materialization_does_not_duplicate_conflicts(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence, _, _ = await create_materialization_conflict(
        task_service,
        test_engine,
        starts_at=datetime(2099, 2, 5, 10, 0),
        ends_at=datetime(2099, 2, 5, 11, 0),
        title="recurring-conflict-deduplicate",
    )

    await task_service.materialize_recurrence_instances(
        TEST_USER_ID,
        (Schedule(starts_at=datetime(2099, 2, 6, 0, 0), ends_at=datetime(2099, 2, 7, 0, 0)),),
    )

    assert await conflict_count(test_engine, recurrence.recurrence_id) == 1
    assert await resolved_conflict_count(test_engine, recurrence.recurrence_id) == 0


@pytest.mark.asyncio
async def test_task_list_excludes_conflicts_when_recurring_tasks_are_excluded(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    await create_materialization_conflict(
        task_service,
        test_engine,
        starts_at=datetime(2099, 2, 10, 10, 0),
        ends_at=datetime(2099, 2, 10, 11, 0),
        title="recurring-conflict-include-recurring",
    )

    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 2, 11, 0, 0),
            due_to=datetime(2099, 2, 11, 23, 59),
            include_recurring=False,
        ),
    )

    assert tasks.conflicts == []


@pytest.mark.asyncio
async def test_task_list_filters_materialization_conflicts(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    await create_materialization_conflict(
        task_service,
        test_engine,
        starts_at=datetime(2099, 2, 15, 10, 0),
        ends_at=datetime(2099, 2, 15, 11, 0),
        title="recurring-conflict-filter",
        priority=TaskPriority.HIGH,
    )
    due_from = datetime(2099, 2, 16, 0, 0)
    due_to = datetime(2099, 2, 16, 23, 59)

    active = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, statuses=(TaskStatus.ACTIVE,)),
    )
    completed = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, statuses=(TaskStatus.COMPLETED,)),
    )
    high_priority = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, priorities=(TaskPriority.HIGH,)),
    )
    low_priority = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, priorities=(TaskPriority.LOW,)),
    )
    tagged = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, tag_ids=(uuid4(),)),
    )
    matching_search = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, search_text="recurring-conflict-filter"),
    )
    missing_search = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(due_from=due_from, due_to=due_to, search_text="missing-conflict-title"),
    )

    assert len(active.conflicts) == 1
    assert completed.conflicts == []
    assert len(high_priority.conflicts) == 1
    assert low_priority.conflicts == []
    assert tagged.conflicts == []
    assert len(matching_search.conflicts) == 1
    assert missing_search.conflicts == []


@pytest.mark.asyncio
async def test_count_tasks_does_not_include_materialization_conflicts(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    await create_materialization_conflict(
        task_service,
        test_engine,
        starts_at=datetime(2099, 2, 20, 10, 0),
        ends_at=datetime(2099, 2, 20, 11, 0),
        title="recurring-conflict-count",
    )

    count = await task_service.count_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 2, 21, 0, 0),
            due_to=datetime(2099, 2, 21, 23, 59),
        ),
    )

    assert count == 1


@pytest.mark.asyncio
async def test_materialization_creates_one_conflict_for_multiple_blocking_tasks(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}recurring-conflict-multiple-blockers",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 2, 25, 10, 0),
                ends_at=datetime(2099, 2, 25, 12, 0),
            ),
            occurrences_limit=3,
        ),
    )
    await delete_generated_occurrence(test_engine, recurrence.recurrence_id, 2)
    await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-conflict-first-blocker",
            due_at=datetime(2099, 2, 26, 11, 0),
            schedule=Schedule(
                starts_at=datetime(2099, 2, 26, 10, 0),
                ends_at=datetime(2099, 2, 26, 11, 0),
            ),
        ),
    )
    await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-conflict-second-blocker",
            due_at=datetime(2099, 2, 26, 12, 0),
            schedule=Schedule(
                starts_at=datetime(2099, 2, 26, 11, 0),
                ends_at=datetime(2099, 2, 26, 12, 0),
            ),
        ),
    )

    await task_service.materialize_recurrence_instances(
        TEST_USER_ID,
        (Schedule(starts_at=datetime(2099, 2, 26, 0, 0), ends_at=datetime(2099, 2, 27, 0, 0)),),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 2, 26, 0, 0),
            due_to=datetime(2099, 2, 26, 23, 59),
        ),
    )

    assert await conflict_count(test_engine, recurrence.recurrence_id) == 1
    assert len(tasks.conflicts) == 1
    assert tasks.conflicts[0].schedule == Schedule(
        starts_at=datetime(2099, 2, 26, 10, 0),
        ends_at=datetime(2099, 2, 26, 12, 0),
    )


@pytest.mark.asyncio
async def test_other_users_tasks_do_not_create_materialization_conflicts(
    task_service: TaskService,
    test_engine: AsyncEngine,
) -> None:
    recurrence, conflict_schedule, _ = await create_materialization_conflict(
        task_service,
        test_engine,
        starts_at=datetime(2099, 3, 1, 10, 0),
        ends_at=datetime(2099, 3, 1, 11, 0),
        title="recurring-conflict-user-isolation",
        blocker_user_id=TEST_OTHER_USER_ID,
    )

    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            due_from=datetime(2099, 3, 2, 0, 0),
            due_to=datetime(2099, 3, 2, 23, 59),
        ),
    )

    assert await conflict_count(test_engine, recurrence.recurrence_id) == 0
    assert tasks.conflicts == []
    assert [task.schedule for task in tasks.tasks] == [conflict_schedule]


@pytest.mark.asyncio
async def test_user_can_skip_recurring_occurrence(
    task_service: TaskService,
) -> None:
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-skip",
            due_at=datetime(2099, 11, 1, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 11, 1, 10, 0),
                ends_at=datetime(2099, 11, 1, 11, 0),
            ),
            occurrences_limit=1,
        ),
    )

    skipped = await task_service.skip_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 11, 1, 10, 0),
    )
    skipped_tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 11, 1, 10, 0),
            ends_to=datetime(2099, 11, 1, 11, 0),
        ),
    )

    assert skipped.is_cancelled
    assert skipped_tasks.tasks == []


@pytest.mark.asyncio
async def test_user_can_update_recurrence_series_schedule(
    task_service: TaskService,
) -> None:
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-update-series",
            due_at=datetime(2099, 11, 2, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 11, 2, 10, 0),
                ends_at=datetime(2099, 11, 2, 11, 0),
            ),
            occurrences_limit=2,
        ),
    )
    await task_service.get_task_occurrences(
        TEST_USER_ID,
        recurrence.template_id,
        Schedule(starts_at=datetime(2099, 11, 2), ends_at=datetime(2099, 11, 4)),
    )

    updated = await task_service.update_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        UpdateTaskRecurrence(
            anchor_date=datetime(2099, 11, 2).date(),
            default_time=datetime(2099, 11, 2, 12).time(),
            default_duration=timedelta(hours=1),
            occurrences_limit=2,
        ),
    )
    occurrences = await task_service.get_task_occurrences(
        TEST_USER_ID,
        recurrence.template_id,
        Schedule(starts_at=datetime(2099, 11, 2), ends_at=datetime(2099, 11, 4)),
    )

    assert updated.schedule == Schedule(
        starts_at=datetime(2099, 11, 2, 12, 0),
        ends_at=datetime(2099, 11, 2, 13, 0),
    )
    assert [item.schedule for item in occurrences] == [
        Schedule(starts_at=datetime(2099, 11, 2, 12, 0), ends_at=datetime(2099, 11, 2, 13, 0)),
        Schedule(starts_at=datetime(2099, 11, 3, 12, 0), ends_at=datetime(2099, 11, 3, 13, 0)),
    ]


@pytest.mark.asyncio
async def test_user_can_stop_recurrence_series_from_date(
    task_service: TaskService,
) -> None:
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-stop-series",
            due_at=datetime(2099, 11, 5, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 11, 5, 10, 0),
                ends_at=datetime(2099, 11, 5, 11, 0),
            ),
            occurrences_limit=3,
        ),
    )
    await task_service.get_task_occurrences(
        TEST_USER_ID,
        recurrence.template_id,
        Schedule(starts_at=datetime(2099, 11, 5), ends_at=datetime(2099, 11, 8)),
    )

    await task_service.stop_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 11, 6, 10, 0),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=datetime(2099, 11, 5, 0, 0),
            ends_to=datetime(2099, 11, 8, 0, 0),
        ),
    )

    assert [item.schedule for item in tasks.tasks] == [
        Schedule(starts_at=datetime(2099, 11, 5, 10, 0), ends_at=datetime(2099, 11, 5, 11, 0))
    ]


@pytest.mark.asyncio
async def test_extending_stopped_recurrence_restores_only_matching_instances(
    task_service: TaskService,
) -> None:
    starts_at = datetime(2099, 12, 10, 10, 0)
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}extend-stopped-recurrence",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
        ),
    )
    skipped_starts_at = starts_at + timedelta(days=3)
    await task_service.skip_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        skipped_starts_at,
    )
    await task_service.stop_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        starts_at + timedelta(days=1),
    )

    await task_service.update_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        UpdateTaskRecurrence(
            anchor_date=starts_at.date(),
            default_time=starts_at.time(),
            default_duration=timedelta(hours=1),
            repeat_until=(starts_at + timedelta(days=4)).date(),
        ),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            search_text=f"{TEST_TITLE_PREFIX}extend-stopped-recurrence",
            starts_from=starts_at,
            ends_to=starts_at + timedelta(days=6),
        ),
    )

    assert [scheduled_start(task) for task in tasks.tasks] == [
        starts_at,
        starts_at + timedelta(days=1),
        starts_at + timedelta(days=2),
        starts_at + timedelta(days=4),
    ]


@pytest.mark.asyncio
async def test_extending_old_recurrence_materializes_current_instances(
    task_service: TaskService,
) -> None:
    current_start = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
    original_start = current_start - timedelta(
        days=settings.recurrence.daily_materialization_days + 5
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        f"{TEST_TITLE_PREFIX}extend-old-recurrence",
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=original_start,
                ends_at=original_start + timedelta(hours=1),
            ),
        ),
    )

    await task_service.update_task_recurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        UpdateTaskRecurrence(
            anchor_date=original_start.date(),
            default_time=original_start.time(),
            default_duration=timedelta(hours=1),
            repeat_until=(current_start + timedelta(days=2)).date(),
        ),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            search_text=f"{TEST_TITLE_PREFIX}extend-old-recurrence",
            starts_from=current_start,
            ends_to=current_start + timedelta(days=3),
        ),
    )

    assert [scheduled_start(task) for task in tasks.tasks] == [
        current_start,
        current_start + timedelta(days=1),
        current_start + timedelta(days=2),
    ]


@pytest.mark.asyncio
async def test_user_can_override_future_not_materialized_occurrence(
    task_service: TaskService,
) -> None:
    task = await task_service.create_task(
        TEST_USER_ID,
        AddTask(
            title=f"{TEST_TITLE_PREFIX}recurring-future-override",
            due_at=datetime(2099, 1, 1, 10, 0),
        ),
    )
    recurrence = await create_task_recurrence_rule(
        task_service,
        TEST_USER_ID,
        task.title,
        scheduled_recurrence(
            frequency=RecurrenceFrequency.DAILY,
            schedule=Schedule(
                starts_at=datetime(2099, 1, 1, 10, 0),
                ends_at=datetime(2099, 1, 1, 11, 0),
            ),
        ),
    )
    override_schedule = Schedule(
        starts_at=datetime(2099, 5, 1, 12, 0),
        ends_at=datetime(2099, 5, 1, 13, 0),
    )

    occurrence = await task_service.update_task_occurrence(
        TEST_USER_ID,
        recurrence.recurrence_id,
        datetime(2099, 5, 1, 10, 0),
        UpdateTaskOccurrence(schedule=override_schedule),
    )
    await task_service.materialize_recurrence_instances(
        TEST_USER_ID,
        (Schedule(starts_at=datetime(2099, 5, 1, 0, 0), ends_at=datetime(2099, 5, 2, 0, 0)),),
    )
    tasks = await task_service.get_tasks(
        TEST_USER_ID,
        ListTasksFilters(
            starts_from=override_schedule.starts_at, ends_to=override_schedule.ends_at
        ),
    )

    assert occurrence.task_id is None
    assert [item.schedule for item in tasks.tasks] == [override_schedule]
