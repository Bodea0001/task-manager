from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from domain.value_objects.tasks import (
    Weekday,
    Schedule,
    TaskPriority,
    TaskStatus,
    RecurrenceFrequency,
    RecurrenceMonthRule,
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


def test_new_task_has_active_status_by_default() -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)
    due_at = ends_at

    # Act
    task = AddTask(
        title="Prepare report",
        due_at=due_at,
        description="Collect notes and send summary",
        schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
    )

    # Assert
    assert task.title == "Prepare report"
    assert task.description == "Collect notes and send summary"
    assert task.due_at == due_at
    assert task.schedule == Schedule(starts_at=starts_at, ends_at=ends_at)
    assert task.status == TaskStatus.ACTIVE
    assert task.priority == TaskPriority.NORMAL


def test_new_task_accepts_priority() -> None:
    # Arrange
    due_at = datetime(2026, 5, 5, 11, 0)

    # Act
    task = AddTask(
        title="Prepare report",
        due_at=due_at,
        priority=TaskPriority.HIGH,
    )

    # Assert
    assert task.priority == TaskPriority.HIGH


def test_new_task_text_fields_are_trimmed() -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act
    task = AddTask(
        title="  Prepare report  ",
        due_at=ends_at,
        description="  Collect notes and send summary  ",
        schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
    )

    # Assert
    assert task.title == "Prepare report"
    assert task.description == "Collect notes and send summary"


def test_new_task_accepts_tag_ids() -> None:
    # Arrange
    tag_id = uuid4()
    starts_at = datetime(2026, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act
    task = AddTask(
        title="Prepare report",
        due_at=ends_at,
        schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
        tag_ids=(tag_id,),
    )

    # Assert
    assert task.tag_ids == (tag_id,)


def test_new_task_accepts_no_schedule() -> None:
    # Arrange
    due_at = datetime(2026, 5, 5, 11, 0)

    # Act
    task = AddTask(title="Prepare report", due_at=due_at)

    # Assert
    assert task.due_at == due_at
    assert task.schedule is None


def test_task_with_deadline_before_start_is_rejected() -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    ends_at = starts_at - timedelta(minutes=1)

    # Act, Assert
    with pytest.raises(ValueError):
        AddTask(
            title="Prepare report",
            due_at=starts_at,
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
        )


@pytest.mark.parametrize(
    "title",
    [
        "",
        "x" * 251,
    ],
)
def test_task_with_invalid_title_is_rejected(title: str) -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act, Assert
    with pytest.raises(ValueError):
        AddTask(
            title=title,
            due_at=ends_at,
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
        )


def test_task_with_empty_description_is_rejected() -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    ends_at = starts_at + timedelta(hours=1)

    # Act, Assert
    with pytest.raises(ValueError):
        AddTask(
            title="Prepare report",
            due_at=ends_at,
            description="",
            schedule=Schedule(starts_at=starts_at, ends_at=ends_at),
        )


def test_empty_task_update_is_rejected() -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        UpdateTaskData()


def test_task_recurrence_accepts_explicit_timing_and_weekdays() -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    recurrence = AddTaskRecurrence(
        frequency=RecurrenceFrequency.WEEKLY,
        anchor_date=starts_at.date(),
        default_time=starts_at.time(),
        default_duration=timedelta(hours=1),
        weekdays=(Weekday.TUESDAY, Weekday.THURSDAY),
        interval=2,
        occurrences_limit=5,
    )

    # Assert
    assert recurrence.frequency == RecurrenceFrequency.WEEKLY
    assert recurrence.interval == 2
    assert recurrence.weekdays == (Weekday.TUESDAY, Weekday.THURSDAY)
    assert recurrence.anchor_date == starts_at.date()
    assert recurrence.default_time == starts_at.time()
    assert recurrence.default_duration == timedelta(hours=1)
    assert recurrence.occurrences_limit == 5


def test_task_recurrence_template_requires_rules() -> None:
    with pytest.raises(ValueError):
        AddTaskRecurrenceTemplate(title="Pay rent", rules=())


def test_task_recurrence_template_accepts_rules() -> None:
    starts_at = datetime(2026, 5, 5, 10, 0)
    recurrence = AddTaskRecurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        anchor_date=starts_at.date(),
        default_time=starts_at.time(),
        month_rule=RecurrenceMonthRule(month_day=starts_at.day),
    )

    template = AddTaskRecurrenceTemplate(title="Pay rent", rules=(recurrence,))

    assert template.rules == (recurrence,)


def test_task_recurrence_template_accepts_tag_ids() -> None:
    starts_at = datetime(2026, 5, 5, 10, 0)
    tag_id = uuid4()
    recurrence = AddTaskRecurrence(
        frequency=RecurrenceFrequency.MONTHLY,
        anchor_date=starts_at.date(),
        default_time=starts_at.time(),
        month_rule=RecurrenceMonthRule(month_day=starts_at.day),
    )

    template = AddTaskRecurrenceTemplate(
        title="Pay rent",
        rules=(recurrence,),
        tag_ids=(tag_id,),
    )

    assert template.tag_ids == (tag_id,)


def test_recurrence_template_filters_accept_tag_ids() -> None:
    tag_id = uuid4()

    filters = ListTaskRecurrenceTemplatesFilters(tag_ids=(tag_id,))

    assert filters.tag_ids == (tag_id,)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"interval": 0},
        {"default_duration": timedelta(0)},
        {"occurrences_limit": 0},
        {"repeat_until": datetime(2026, 5, 4).date()},
        {
            "repeat_until": datetime(2026, 5, 6).date(),
            "occurrences_limit": 5,
        },
    ],
)
def test_task_recurrence_with_invalid_rule_is_rejected(kwargs: dict) -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    with pytest.raises(ValueError):
        AddTaskRecurrence(
            frequency=RecurrenceFrequency.DAILY,
            anchor_date=starts_at.date(),
            default_time=starts_at.time(),
            **kwargs,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "repeat_until": datetime(2026, 5, 6).date(),
            "occurrences_limit": 5,
        },
        {"repeat_until": datetime(2026, 5, 4).date()},
        {"default_duration": timedelta(0)},
        {"occurrences_limit": 0},
    ],
)
def test_task_recurrence_update_with_invalid_rule_is_rejected(kwargs: dict) -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    with pytest.raises(ValueError):
        UpdateTaskRecurrence(
            anchor_date=starts_at.date(),
            default_time=starts_at.time(),
            **kwargs,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency": RecurrenceFrequency.DAILY},
        {"interval": 2},
        {"weekdays": (Weekday.MONDAY,)},
        {"month_rule": RecurrenceMonthRule(month_day=5)},
    ],
)
def test_task_recurrence_update_rejects_immutable_rule_fields(kwargs: dict) -> None:
    # Arrange
    starts_at = datetime(2026, 5, 5, 10, 0)
    with pytest.raises(TypeError):
        UpdateTaskRecurrence(
            anchor_date=starts_at.date(),
            default_time=starts_at.time(),
            **kwargs,
        )


def test_task_occurrence_update_requires_change() -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        UpdateTaskOccurrence()


def test_task_update_accepts_priority() -> None:
    # Act
    update_data = UpdateTaskData(priority=TaskPriority.URGENT)

    # Assert
    assert update_data.priority == TaskPriority.URGENT


def test_task_update_text_fields_are_trimmed() -> None:
    # Act
    update_data = UpdateTaskData(
        title="  Prepare report  ",
        description="  Collect notes and send summary  ",
    )

    # Assert
    assert update_data.title == "Prepare report"
    assert update_data.description == "Collect notes and send summary"


@pytest.mark.parametrize(
    "data",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 251},
        {"description": ""},
        {"description": "   "},
    ],
)
def test_task_update_with_invalid_text_is_rejected(data: dict) -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        UpdateTaskData(**data)


def test_task_list_filter_with_invalid_start_range_is_rejected() -> None:
    # Arrange
    starts_from = datetime(2026, 5, 5, 11, 0)
    starts_to = datetime(2026, 5, 5, 10, 0)

    # Act, Assert
    with pytest.raises(ValueError):
        ListTasksFilters(starts_from=starts_from, starts_to=starts_to)


@pytest.mark.parametrize(
    "filters",
    [
        {
            "due_from": datetime(2026, 5, 5, 11, 0),
            "due_to": datetime(2026, 5, 5, 10, 0),
        },
        {
            "ends_from": datetime(2026, 5, 5, 11, 0),
            "ends_to": datetime(2026, 5, 5, 10, 0),
        },
        {
            "starts_from": datetime(2026, 5, 5, 11, 0),
            "ends_to": datetime(2026, 5, 5, 10, 0),
        },
    ],
)
def test_task_list_filter_with_invalid_ranges_is_rejected(filters: dict) -> None:
    # Act, Assert
    with pytest.raises(ValueError):
        ListTasksFilters(**filters)


def test_task_list_filter_accepts_tag_ids() -> None:
    # Arrange
    tag_id = uuid4()

    # Act
    filters = ListTasksFilters(tag_ids=(tag_id,))

    # Assert
    assert filters.tag_ids == (tag_id,)


def test_task_list_filter_accepts_search_text() -> None:
    # Act
    filters = ListTasksFilters(search_text="invoice report")

    # Assert
    assert filters.search_text == "invoice report"


def test_task_list_filter_accepts_priorities() -> None:
    # Act
    filters = ListTasksFilters(priorities=(TaskPriority.HIGH, TaskPriority.URGENT))

    # Assert
    assert filters.priorities == (TaskPriority.HIGH, TaskPriority.URGENT)
