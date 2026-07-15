from uuid import UUID
from typing import Any
from datetime import date, datetime, time, timedelta

from langchain.tools import tool

import exceptions as app_exc
from dto.tasks import (
    AddTask,
    UpdateTaskData,
    ListTasksFilters,
    AddTaskRecurrence,
    UpdateTaskRecurrence,
    UpdateTaskOccurrence,
    AddTaskRecurrenceTemplate,
    ListTaskRecurrenceTemplatesFilters,
)
from agents.schemas.tools import (
    HiddenRuntime,
    AddTaskRecurrenceData,
    RecurrenceMonthRuleData,
    CancelTaskInput,
    CompleteTaskInput,
    CountTaskRecurrenceTemplatesInput,
    CountTasksInput,
    CreateTaskInput,
    DeleteTaskScheduleInput,
    FindNearestFreeScheduleInput,
    GetFreeTimeInput,
    GetOverdueTasksInput,
    GetRecurrenceInstanceByTaskInput,
    GetTaskInput,
    GetTaskHistoryInput,
    GetTaskOccurrencesInput,
    GetTaskRecurrenceRulesInput,
    GetTaskRecurrenceTemplateHistoryInput,
    GetTaskRecurrenceTemplateInput,
    ListTasksInput,
    ReopenTaskInput,
    AddTaskRecurrenceRuleInput,
    AddTaskRecurrenceTemplateInput,
    ListTaskRecurrenceTemplatesInput,
    RecurrenceTemplateTagInput,
    ScheduleWindowInput,
    SkipTaskOccurrenceInput,
    StopTaskRecurrenceInput,
    TaskTagInput,
    UpdateTaskInput,
    UpdateTaskOccurrenceInput,
    UpdateTaskRecurrenceInput,
    UpdateTaskScheduleInput,
)
from domain.value_objects.audit import AuditEvent
from domain.value_objects.tasks import (
    Task,
    FreeTime,
    Schedule,
    TaskPriority,
    TaskStatus,
    RecurrenceFrequency,
    RecurrenceMonthRule,
    Weekday,
    TaskOccurrence,
    TaskRecurrence,
    ScheduleAvailability,
    TaskRecurrenceTemplate,
)


@tool(
    "get_task",
    description="Get one task by id when the user already identified the exact task.",
    args_schema=GetTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_task(
    task_id: UUID,
    runtime: HiddenRuntime,
) -> dict[str, Any]:
    """Get one task by id.

    Use this only when the user already identified the exact task.

    Args:
        task_id: Exact task id to retrieve.
    """
    try:
        task = await runtime.context.task_service.get_task(runtime.context.user_id, task_id)
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "list_tasks",
    description="List or search the user's tasks using safe filters.",
    args_schema=ListTasksInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def list_tasks(
    runtime: HiddenRuntime,
    tag_ids: tuple[UUID, ...] = (),
    statuses: tuple[TaskStatus, ...] = (),
    priorities: tuple[TaskPriority, ...] = (),
    search_text: str | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    ends_from: datetime | None = None,
    ends_to: datetime | None = None,
    include_recurring: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List or search the user's tasks.

    Use this for lookup, disambiguation, and non-mutating task review.

    Args:
        tag_ids: Optional tag ids used to filter the user's tasks.
        statuses: Optional task status filters.
        priorities: Optional task priority filters.
        search_text: Optional text to search in task titles.
        due_from: Optional inclusive lower bound for task due_at.
        due_to: Optional inclusive upper bound for task due_at.
        starts_from: Optional inclusive lower bound for schedule starts_at.
        starts_to: Optional inclusive upper bound for schedule starts_at.
        ends_from: Optional inclusive lower bound for schedule ends_at.
        ends_to: Optional inclusive upper bound for schedule ends_at.
        include_recurring: Whether recurring task occurrences should be included.
        limit: Maximum number of tasks to return.
        offset: Number of matching tasks to skip.
    """
    try:
        filters = ListTasksFilters(
            tag_ids=tag_ids,
            statuses=statuses,
            priorities=priorities,
            search_text=search_text,
            due_from=due_from,
            due_to=due_to,
            starts_from=starts_from,
            starts_to=starts_to,
            ends_from=ends_from,
            ends_to=ends_to,
            include_recurring=include_recurring,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    task_list = await runtime.context.task_service.get_tasks(runtime.context.user_id, filters)

    return {
        "status": "ok",
        "count": len(task_list.tasks),
        "tasks": [_task_to_dict(task) for task in task_list.tasks],
        "conflicts": [_task_to_dict(task) for task in task_list.conflicts],
    }


@tool(
    "count_tasks",
    description="Count the user's tasks using the same safe filters as list_tasks.",
    args_schema=CountTasksInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def count_tasks(
    runtime: HiddenRuntime,
    tag_ids: tuple[UUID, ...] = (),
    statuses: tuple[TaskStatus, ...] = (),
    priorities: tuple[TaskPriority, ...] = (),
    search_text: str | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    ends_from: datetime | None = None,
    ends_to: datetime | None = None,
    include_recurring: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Count the user's tasks with filters.

    Args:
        tag_ids: Optional tag ids used to filter the user's tasks.
        statuses: Optional task status filters.
        priorities: Optional task priority filters.
        search_text: Optional text to search in task titles.
        due_from: Optional inclusive lower bound for task due_at.
        due_to: Optional inclusive upper bound for task due_at.
        starts_from: Optional inclusive lower bound for schedule starts_at.
        starts_to: Optional inclusive upper bound for schedule starts_at.
        ends_from: Optional inclusive lower bound for schedule ends_at.
        ends_to: Optional inclusive upper bound for schedule ends_at.
        include_recurring: Whether recurring task occurrences should be included.
        limit: Maximum number of tasks to consider.
        offset: Number of matching tasks to skip.
    """
    try:
        filters = ListTasksFilters(
            tag_ids=tag_ids,
            statuses=statuses,
            priorities=priorities,
            search_text=search_text,
            due_from=due_from,
            due_to=due_to,
            starts_from=starts_from,
            starts_to=starts_to,
            ends_from=ends_from,
            ends_to=ends_to,
            include_recurring=include_recurring,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    count = await runtime.context.task_service.count_tasks(runtime.context.user_id, filters)
    return {"status": "ok", "count": count}


@tool(
    "get_overdue_tasks",
    description="List overdue tasks for the authenticated user.",
    args_schema=GetOverdueTasksInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_overdue_tasks(
    runtime: HiddenRuntime,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List overdue tasks.

    Args:
        limit: Maximum number of tasks to return.
        offset: Number of tasks to skip.
    """
    tasks = await runtime.context.task_service.get_overdue_tasks(
        runtime.context.user_id, limit=limit, offset=offset
    )
    return {"status": "ok", "count": len(tasks), "tasks": [_task_to_dict(task) for task in tasks]}


@tool(
    "create_task",
    description="Create one task for the authenticated user.",
    args_schema=CreateTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def create_task(
    runtime: HiddenRuntime,
    title: str,
    due_at: datetime,
    description: str | None = None,
    tag_ids: tuple[UUID, ...] = (),
    status: TaskStatus = TaskStatus.ACTIVE,
    priority: TaskPriority = TaskPriority.NORMAL,
    schedule: Schedule | None = None,
) -> dict[str, Any]:
    """Create one task for the authenticated user.

    Args:
        title: Task title.
        due_at: Absolute task deadline.
        description: Optional task details.
        tag_ids: Optional tag ids to attach to the task.
        status: Initial task status.
        priority: Task priority inferred from the request.
        schedule: Optional scheduled execution window for the task.
    """
    try:
        task = await runtime.context.task_service.create_task(
            runtime.context.user_id,
            AddTask(
                title=title,
                due_at=due_at,
                description=description,
                tag_ids=tag_ids,
                status=status,
                priority=priority,
                schedule=schedule,
            ),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)
    except app_exc.TaskScheduleOverlap:
        return _tool_error("conflict", "Task schedule overlaps another task.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "update_task",
    description="Update one task by exact task id.",
    args_schema=UpdateTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def update_task(
    task_id: UUID,
    runtime: HiddenRuntime,
    title: str | None = None,
    description: str | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_at: datetime | None = None,
    schedule: Schedule | None = None,
) -> dict[str, Any]:
    """Update one task by exact task id.

    Args:
        task_id: Exact task id to update.
        title: New task title. Omit or null leaves it unchanged.
        description: New task details. Omit or null leaves it unchanged.
        status: New task status. Omit or null leaves it unchanged.
        priority: New task priority. Omit or null leaves it unchanged.
        due_at: New task deadline. Omit or null leaves it unchanged.
        schedule: New scheduled execution window. Use delete_task_schedule to remove it.
    """
    try:
        task = await runtime.context.task_service.update_task(
            runtime.context.user_id,
            task_id,
            UpdateTaskData(
                title=title,
                description=description,
                status=status,
                priority=priority,
                due_at=due_at,
                schedule=schedule,
            ),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)
    except app_exc.TaskScheduleOverlap:
        return _tool_error("conflict", "Task schedule overlaps another task.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "complete_task",
    description="Complete one task by exact task id.",
    args_schema=CompleteTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def complete_task(
    task_id: UUID,
    runtime: HiddenRuntime,
) -> dict[str, Any]:
    """Complete one task by exact task id.

    Use this only after task identity is unambiguous.

    Args:
        task_id: Exact task id to complete.
    """
    try:
        task = await runtime.context.task_service.complete_task(runtime.context.user_id, task_id)
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "reopen_task",
    description="Reopen one completed or cancelled task by exact task id.",
    args_schema=ReopenTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def reopen_task(task_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Reopen one task by exact task id.

    Args:
        task_id: Exact task id to reopen.
    """
    try:
        task = await runtime.context.task_service.reopen_task(runtime.context.user_id, task_id)
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "cancel_task",
    description="Cancel one task by exact task id.",
    args_schema=CancelTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def cancel_task(task_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Cancel one task by exact task id.

    Args:
        task_id: Exact task id to cancel.
    """
    try:
        task = await runtime.context.task_service.cancel_task(runtime.context.user_id, task_id)
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "get_task_history",
    description="Get audit history for one task by exact task id.",
    args_schema=GetTaskHistoryInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_task_history(
    task_id: UUID,
    runtime: HiddenRuntime,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Get task audit history.

    Args:
        task_id: Exact task id.
        limit: Maximum history events to return.
        offset: Number of history events to skip.
    """
    try:
        events = await runtime.context.task_service.get_task_history(
            runtime.context.user_id, task_id, limit=limit, offset=offset
        )
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {"status": "ok", "events": [_audit_event_to_dict(event) for event in events]}


@tool(
    "update_task_schedule",
    description="Set or replace the schedule window for one task by exact task id.",
    args_schema=UpdateTaskScheduleInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def update_task_schedule(
    task_id: UUID,
    runtime: HiddenRuntime,
    schedule: Schedule,
) -> dict[str, Any]:
    """Set or replace a task schedule.

    Args:
        task_id: Exact task id to update.
        schedule: New scheduled execution window.
    """
    try:
        task = await runtime.context.task_service.update_task(
            runtime.context.user_id,
            task_id,
            UpdateTaskData(schedule=schedule),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)
    except app_exc.TaskScheduleOverlap:
        return _tool_error("conflict", "Task schedule overlaps another task.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "get_free_time",
    description="Find free time inside one or more schedule windows.",
    args_schema=GetFreeTimeInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_free_time(runtime: HiddenRuntime, windows: tuple[Schedule, ...]) -> dict[str, Any]:
    """Find free time in windows.

    Args:
        windows: Schedule windows to inspect.
    """
    try:
        free_time = await runtime.context.task_service.get_free_time(
            runtime.context.user_id, windows
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    return {"status": "ok", "free_time": [_free_time_to_dict(item) for item in free_time]}


@tool(
    "check_schedule_availability",
    description="Check whether a schedule window conflicts with existing user tasks.",
    args_schema=ScheduleWindowInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def check_schedule_availability(runtime: HiddenRuntime, window: Schedule) -> dict[str, Any]:
    """Check schedule availability.

    Args:
        window: Schedule window to check.
    """
    try:
        availability = await runtime.context.task_service.check_schedule_availability(
            runtime.context.user_id, window
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    return {"status": "ok", "availability": _schedule_availability_to_dict(availability)}


@tool(
    "find_nearest_free_schedule",
    description="Find the nearest free schedule slot for a duration.",
    args_schema=FindNearestFreeScheduleInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def find_nearest_free_schedule(
    runtime: HiddenRuntime,
    duration_minutes: int,
    excluded_windows: tuple[Schedule, ...] = (),
    search_from: datetime | None = None,
) -> dict[str, Any]:
    """Find nearest free schedule slot.

    Args:
        duration_minutes: Desired duration in minutes.
        excluded_windows: Existing excluded windows.
        search_from: Optional search start datetime.
    """
    try:
        schedule = await runtime.context.task_service.find_nearest_free_schedule(
            runtime.context.user_id,
            duration=timedelta(minutes=duration_minutes),
            excluded_windows=excluded_windows,
            search_from=search_from,
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)

    return {"status": "ok", "schedule": _schedule_to_dict(schedule)}


@tool(
    "delete_task_schedule",
    description="Remove the schedule from one task without deleting the task.",
    args_schema=DeleteTaskScheduleInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def delete_task_schedule(task_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Remove the schedule from a task.

    Args:
        task_id: Exact task id.
    """
    try:
        task = await runtime.context.task_service.delete_schedule_from_task(
            runtime.context.user_id, task_id
        )
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "add_tag_to_task",
    description="Attach one tag to one task by exact ids.",
    args_schema=TaskTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def add_tag_to_task(task_id: UUID, tag_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Attach a tag to a task.

    Args:
        task_id: Exact task id.
        tag_id: Exact tag id.
    """
    try:
        task = await runtime.context.task_service.add_tag_to_task(
            runtime.context.user_id, task_id, tag_id
        )
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "remove_tag_from_task",
    description="Remove one tag from one task by exact ids.",
    args_schema=TaskTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def remove_tag_from_task(
    task_id: UUID, tag_id: UUID, runtime: HiddenRuntime
) -> dict[str, Any]:
    """Remove a tag from a task.

    Args:
        task_id: Exact task id.
        tag_id: Exact tag id.
    """
    try:
        task = await runtime.context.task_service.delete_tag_from_task(
            runtime.context.user_id, task_id, tag_id
        )
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)

    return {"status": "ok", "task": _task_to_dict(task)}


@tool(
    "get_task_recurrence_template",
    description="Get one recurrence template by exact id.",
    args_schema=GetTaskRecurrenceTemplateInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_task_recurrence_template(template_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Get one recurrence template.

    Args:
        template_id: Exact recurrence template id.
    """
    try:
        template = await runtime.context.task_service.get_task_recurrence_template(
            runtime.context.user_id, template_id
        )
    except app_exc.RecurrenceTemplateNotFound:
        return _tool_error("not_found", "Recurrence template not found.", retryable=False)

    return {"status": "ok", "template": _recurrence_template_to_dict(template)}


@tool(
    "list_task_recurrence_templates",
    description="List recurrence templates using safe filters.",
    args_schema=ListTaskRecurrenceTemplatesInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def list_task_recurrence_templates(
    runtime: HiddenRuntime,
    tag_ids: tuple[UUID, ...] = (),
    priorities: tuple[TaskPriority, ...] = (),
    frequencies: tuple[RecurrenceFrequency, ...] = (),
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List recurrence templates.

    Args:
        tag_ids: Optional tag filters.
        priorities: Optional priority filters.
        frequencies: Optional recurrence frequency filters.
        limit: Maximum templates to return.
        offset: Templates to skip.
    """
    filters = ListTaskRecurrenceTemplatesFilters(
        tag_ids=tag_ids,
        priorities=priorities,
        frequencies=frequencies,
        limit=limit,
        offset=offset,
    )
    templates = await runtime.context.task_service.get_task_recurrence_templates(
        runtime.context.user_id, filters
    )
    return {
        "status": "ok",
        "count": len(templates),
        "templates": [_recurrence_template_to_dict(template) for template in templates],
    }


@tool(
    "count_task_recurrence_templates",
    description="Count recurrence templates using the same safe filters as list_task_recurrence_templates.",
    args_schema=CountTaskRecurrenceTemplatesInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def count_task_recurrence_templates(
    runtime: HiddenRuntime,
    tag_ids: tuple[UUID, ...] = (),
    priorities: tuple[TaskPriority, ...] = (),
    frequencies: tuple[RecurrenceFrequency, ...] = (),
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Count recurrence templates.

    Args:
        tag_ids: Optional tag filters.
        priorities: Optional priority filters.
        frequencies: Optional recurrence frequency filters.
        limit: Maximum templates to consider.
        offset: Templates to skip.
    """
    filters = ListTaskRecurrenceTemplatesFilters(
        tag_ids=tag_ids,
        priorities=priorities,
        frequencies=frequencies,
        limit=limit,
        offset=offset,
    )
    count = await runtime.context.task_service.count_task_recurrence_templates(
        runtime.context.user_id, filters
    )
    return {"status": "ok", "count": count}


@tool(
    "create_task_recurrence_template",
    description="Create a recurrence template with one or more recurrence rules.",
    args_schema=AddTaskRecurrenceTemplateInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def create_task_recurrence_template(
    runtime: HiddenRuntime,
    title: str,
    rules: tuple[AddTaskRecurrenceData, ...],
    description: str | None = None,
    tag_ids: tuple[UUID, ...] = (),
    priority: TaskPriority = TaskPriority.NORMAL,
) -> dict[str, Any]:
    """Create a recurrence template.

    Args:
        title: Template title.
        rules: One or more recurrence rules.
        description: Optional details.
        tag_ids: Optional tag ids.
        priority: Template priority.
    """
    try:
        template = await runtime.context.task_service.add_task_recurrence_template(
            runtime.context.user_id,
            AddTaskRecurrenceTemplate(
                title=title,
                rules=tuple(
                    AddTaskRecurrence(
                        frequency=rule.frequency,
                        anchor_date=rule.anchor_date,
                        default_time=rule.default_time,
                        interval=rule.interval,
                        default_duration=rule.default_duration,
                        weekdays=rule.weekdays,
                        month_rule=_month_rule_to_domain(rule.month_rule),
                        repeat_until=rule.repeat_until,
                        occurrences_limit=rule.occurrences_limit,
                    )
                    for rule in rules
                ),
                description=description,
                tag_ids=tag_ids,
                priority=priority,
            ),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.TagNotFound:
        return _tool_error("not_found", "Tag not found or not accessible.", retryable=False)

    return {"status": "ok", "template": _recurrence_template_to_dict(template)}


@tool(
    "get_task_recurrence_rules",
    description="List recurrence rules for one recurrence template.",
    args_schema=GetTaskRecurrenceRulesInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_task_recurrence_rules(template_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """List recurrence rules.

    Args:
        template_id: Exact recurrence template id.
    """
    try:
        rules = await runtime.context.task_service.get_task_recurrence_rules(
            runtime.context.user_id, template_id
        )
    except app_exc.RecurrenceTemplateNotFound:
        return _tool_error("not_found", "Recurrence template not found.", retryable=False)

    return {"status": "ok", "rules": [_recurrence_rule_to_dict(rule) for rule in rules]}


@tool(
    "add_task_recurrence_rule",
    description="Add one recurrence rule to an existing recurrence template.",
    args_schema=AddTaskRecurrenceRuleInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def add_task_recurrence_rule(
    template_id: UUID,
    runtime: HiddenRuntime,
    frequency: RecurrenceFrequency,
    anchor_date: date,
    default_time: time,
    interval: int = 1,
    default_duration: timedelta | None = None,
    weekdays: tuple[Weekday, ...] = (),
    month_rule: RecurrenceMonthRuleData | None = None,
    repeat_until: date | None = None,
    occurrences_limit: int | None = None,
) -> dict[str, Any]:
    """Add a recurrence rule.

    Args:
        template_id: Exact recurrence template id.
        frequency: Recurrence frequency.
        anchor_date: Date of the first occurrence.
        default_time: Deadline time for each occurrence.
        interval: Positive interval.
        default_duration: Optional duration used to create a schedule.
        weekdays: Weekdays for a weekly rule.
        month_rule: Calendar selector for a monthly rule.
        repeat_until: Optional inclusive end date.
        occurrences_limit: Optional occurrence limit.
    """
    try:
        rule = await runtime.context.task_service.add_task_recurrence_rule(
            runtime.context.user_id,
            template_id,
            AddTaskRecurrence(
                frequency=frequency,
                anchor_date=anchor_date,
                default_time=default_time,
                interval=interval,
                default_duration=default_duration,
                weekdays=weekdays,
                month_rule=_month_rule_to_domain(month_rule),
                repeat_until=repeat_until,
                occurrences_limit=occurrences_limit,
            ),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.RecurrenceTemplateNotFound:
        return _tool_error("not_found", "Recurrence template not found.", retryable=False)

    return {"status": "ok", "rule": _recurrence_rule_to_dict(rule)}


@tool(
    "update_task_recurrence_rule",
    description="Update one recurrence rule timing or end condition.",
    args_schema=UpdateTaskRecurrenceInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def update_task_recurrence_rule(
    recurrence_id: UUID,
    runtime: HiddenRuntime,
    anchor_date: date,
    default_time: time,
    default_duration: timedelta | None = None,
    repeat_until: date | None = None,
    occurrences_limit: int | None = None,
) -> dict[str, Any]:
    """Update a recurrence rule.

    Args:
        recurrence_id: Exact recurrence rule id.
        anchor_date: Date of the first occurrence.
        default_time: Deadline time for each occurrence.
        default_duration: Optional duration used to create a schedule.
        repeat_until: Optional inclusive end date.
        occurrences_limit: Optional occurrence limit.
    """
    try:
        rule = await runtime.context.task_service.update_task_recurrence(
            runtime.context.user_id,
            recurrence_id,
            UpdateTaskRecurrence(
                anchor_date=anchor_date,
                default_time=default_time,
                default_duration=default_duration,
                repeat_until=repeat_until,
                occurrences_limit=occurrences_limit,
            ),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.RecurrenceRuleNotFound:
        return _tool_error("not_found", "Recurrence rule not found.", retryable=False)

    return {"status": "ok", "rule": _recurrence_rule_to_dict(rule)}


@tool(
    "stop_task_recurrence",
    description="Stop one recurrence rule from an absolute datetime.",
    args_schema=StopTaskRecurrenceInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def stop_task_recurrence(
    recurrence_id: UUID, stop_from: datetime, runtime: HiddenRuntime
) -> dict[str, Any]:
    """Stop a recurrence rule.

    Args:
        recurrence_id: Exact recurrence rule id.
        stop_from: Datetime to stop from.
    """
    try:
        rule = await runtime.context.task_service.stop_task_recurrence(
            runtime.context.user_id, recurrence_id, stop_from
        )
    except app_exc.RecurrenceRuleNotFound:
        return _tool_error("not_found", "Recurrence rule not found.", retryable=False)

    return {"status": "ok", "rule": _recurrence_rule_to_dict(rule)}


@tool(
    "get_task_occurrences",
    description="List recurrence occurrences for a template inside a time window.",
    args_schema=GetTaskOccurrencesInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_task_occurrences(
    template_id: UUID, window: Schedule, runtime: HiddenRuntime
) -> dict[str, Any]:
    """List recurrence occurrences.

    Args:
        template_id: Exact recurrence template id.
        window: Lookup window.
    """
    try:
        occurrences = await runtime.context.task_service.get_task_occurrences(
            runtime.context.user_id, template_id, window
        )
    except app_exc.RecurrenceTemplateNotFound:
        return _tool_error("not_found", "Recurrence template not found.", retryable=False)

    return {"status": "ok", "occurrences": [_occurrence_to_dict(item) for item in occurrences]}


@tool(
    "get_recurrence_instance_by_task",
    description="Get recurrence occurrence metadata for one materialized task id.",
    args_schema=GetRecurrenceInstanceByTaskInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_recurrence_instance_by_task(task_id: UUID, runtime: HiddenRuntime) -> dict[str, Any]:
    """Get recurrence occurrence metadata by task id.

    Args:
        task_id: Exact materialized task id.
    """
    try:
        occurrence = await runtime.context.task_service.get_recurrence_instance_by_task_id(
            runtime.context.user_id, task_id
        )
    except app_exc.TaskNotFound:
        return _tool_error("not_found", "Task not found or not accessible.", retryable=False)

    return {
        "status": "ok",
        "occurrence": _occurrence_to_dict(occurrence) if occurrence is not None else None,
    }


@tool(
    "update_task_occurrence",
    description="Update or cancel one recurrence occurrence override.",
    args_schema=UpdateTaskOccurrenceInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def update_task_occurrence(
    recurrence_id: UUID,
    original_starts_at: datetime,
    runtime: HiddenRuntime,
    title: str | None = None,
    description: str | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_at: datetime | None = None,
    schedule: Schedule | None = None,
    is_cancelled: bool = False,
) -> dict[str, Any]:
    """Update one recurrence occurrence.

    Args:
        recurrence_id: Exact recurrence rule id.
        original_starts_at: Original occurrence start datetime.
        title: Optional title override.
        description: Optional details override.
        status: Optional status override.
        priority: Optional priority override.
        due_at: Optional due_at override.
        schedule: Optional schedule override.
        is_cancelled: Whether to cancel the occurrence.
    """
    try:
        occurrence = await runtime.context.task_service.update_task_occurrence(
            runtime.context.user_id,
            recurrence_id,
            original_starts_at,
            UpdateTaskOccurrence(
                title=title,
                description=description,
                status=status,
                priority=priority,
                due_at=due_at,
                schedule=schedule,
                is_cancelled=is_cancelled,
            ),
        )
    except ValueError as exc:
        return _tool_error("invalid_input", str(exc), retryable=False)
    except app_exc.RecurrenceRuleNotFound:
        return _tool_error("not_found", "Recurrence rule not found.", retryable=False)

    return {"status": "ok", "occurrence": _occurrence_to_dict(occurrence)}


@tool(
    "skip_task_occurrence",
    description="Skip one recurrence occurrence by original start datetime.",
    args_schema=SkipTaskOccurrenceInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def skip_task_occurrence(
    recurrence_id: UUID, original_starts_at: datetime, runtime: HiddenRuntime
) -> dict[str, Any]:
    """Skip one recurrence occurrence.

    Args:
        recurrence_id: Exact recurrence rule id.
        original_starts_at: Original occurrence start datetime.
    """
    try:
        occurrence = await runtime.context.task_service.skip_task_occurrence(
            runtime.context.user_id, recurrence_id, original_starts_at
        )
    except app_exc.RecurrenceRuleNotFound:
        return _tool_error("not_found", "Recurrence rule not found.", retryable=False)

    return {"status": "ok", "occurrence": _occurrence_to_dict(occurrence)}


@tool(
    "get_task_recurrence_template_history",
    description="Get audit history for one recurrence template.",
    args_schema=GetTaskRecurrenceTemplateHistoryInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def get_task_recurrence_template_history(
    template_id: UUID,
    runtime: HiddenRuntime,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Get recurrence template audit history.

    Args:
        template_id: Exact recurrence template id.
        limit: Maximum history events to return.
        offset: History events to skip.
    """
    try:
        events = await runtime.context.task_service.get_task_recurrence_template_history(
            runtime.context.user_id, template_id, limit=limit, offset=offset
        )
    except app_exc.RecurrenceTemplateNotFound:
        return _tool_error("not_found", "Recurrence template not found.", retryable=False)

    return {"status": "ok", "events": [_audit_event_to_dict(event) for event in events]}


@tool(
    "add_tag_to_recurrence_template",
    description="Attach a tag to one recurrence template by exact ids.",
    args_schema=RecurrenceTemplateTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def add_tag_to_recurrence_template(
    template_id: UUID, tag_id: UUID, runtime: HiddenRuntime
) -> dict[str, Any]:
    """Attach a tag to a recurrence template.

    Args:
        template_id: Exact recurrence template id.
        tag_id: Exact tag id.
    """
    try:
        template = await runtime.context.task_service.add_tag_to_task_recurrence_template(
            runtime.context.user_id, template_id, tag_id
        )
    except app_exc.NotFound:
        return _tool_error("not_found", "Template or tag not found.", retryable=False)

    return {"status": "ok", "template": _recurrence_template_to_dict(template)}


@tool(
    "remove_tag_from_recurrence_template",
    description="Remove a tag from one recurrence template by exact ids.",
    args_schema=RecurrenceTemplateTagInput,
    parse_docstring=True,
    error_on_invalid_docstring=False,
)
async def remove_tag_from_recurrence_template(
    template_id: UUID, tag_id: UUID, runtime: HiddenRuntime
) -> dict[str, Any]:
    """Remove a tag from a recurrence template.

    Args:
        template_id: Exact recurrence template id.
        tag_id: Exact tag id.
    """
    try:
        template = await runtime.context.task_service.delete_tag_from_task_recurrence_template(
            runtime.context.user_id, template_id, tag_id
        )
    except app_exc.NotFound:
        return _tool_error("not_found", "Template or tag not found.", retryable=False)

    return {"status": "ok", "template": _recurrence_template_to_dict(template)}


def _tool_error(status: str, message: str, *, retryable: bool) -> dict[str, Any]:
    return {"status": status, "message": message, "retryable": retryable}


def _task_to_dict(task: Task) -> dict[str, Any]:
    return {
        "task_id": str(task.task_id),
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority.value,
        "due_at": task.due_at.isoformat(),
        "description": task.description,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "schedule": _schedule_to_dict(task.schedule),
        "tags": [{"tag_id": str(tag.tag_id), "name": tag.name} for tag in task.tags],
    }


def _schedule_to_dict(schedule: Schedule | None) -> dict[str, str] | None:
    if schedule is None:
        return None

    return {
        "starts_at": schedule.starts_at.isoformat(),
        "ends_at": schedule.ends_at.isoformat(),
    }


def _free_time_to_dict(free_time: FreeTime) -> dict[str, str]:
    return {
        "starts_at": free_time.starts_at.isoformat(),
        "ends_at": free_time.ends_at.isoformat(),
    }


def _schedule_availability_to_dict(availability: ScheduleAvailability) -> dict[str, Any]:
    return {
        "can_add_task": availability.can_add_task,
        "blocking_tasks": [_task_to_dict(task) for task in availability.blocking_tasks],
    }


def _audit_event_to_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "actor_user_id": str(event.actor_user_id),
        "entity_type": event.entity_type.value,
        "entity_id": str(event.entity_id),
        "event_type": event.event_type.value,
        "occurred_at": event.occurred_at.isoformat(),
        "data": event.data,
    }


def _recurrence_template_to_dict(template: TaskRecurrenceTemplate) -> dict[str, Any]:
    return {
        "template_id": str(template.template_id),
        "title": template.title,
        "priority": template.priority.value,
        "created_at": template.created_at.isoformat(),
        "description": template.description,
        "tags": [{"tag_id": str(tag.tag_id), "name": tag.name} for tag in template.tags],
        "rules": [_recurrence_rule_to_dict(rule) for rule in template.rules],
    }


def _recurrence_rule_to_dict(rule: TaskRecurrence) -> dict[str, Any]:
    return {
        "recurrence_id": str(rule.recurrence_id),
        "template_id": str(rule.template_id),
        "frequency": rule.frequency.value,
        "interval": rule.interval,
        "anchor_date": rule.anchor_date.isoformat(),
        "default_time": rule.default_time.isoformat(),
        "default_duration_seconds": (
            rule.default_duration.total_seconds() if rule.default_duration is not None else None
        ),
        "weekdays": [int(weekday) for weekday in rule.weekdays],
        "month_rule": (
            {
                "month_day": rule.month_rule.month_day,
                "week_of_month": rule.month_rule.week_of_month,
                "weekday": int(rule.month_rule.weekday)
                if rule.month_rule.weekday is not None
                else None,
                "business_day_policy": rule.month_rule.business_day_policy.value,
            }
            if rule.month_rule is not None
            else None
        ),
        "schedule": _schedule_to_dict(rule.schedule) if rule.schedule is not None else None,
        "repeat_until": rule.repeat_until.isoformat() if rule.repeat_until else None,
        "occurrences_limit": rule.occurrences_limit,
    }


def _occurrence_to_dict(occurrence: TaskOccurrence) -> dict[str, Any]:
    return {
        "recurrence_id": str(occurrence.recurrence_id),
        "task_id": str(occurrence.task_id) if occurrence.task_id else None,
        "original_starts_at": occurrence.original_starts_at.isoformat(),
        "due_at": occurrence.due_at.isoformat(),
        "schedule": (
            _schedule_to_dict(occurrence.schedule) if occurrence.schedule is not None else None
        ),
        "is_cancelled": occurrence.is_cancelled,
    }


def _month_rule_to_domain(rule: RecurrenceMonthRuleData | None) -> RecurrenceMonthRule | None:
    if rule is None:
        return None
    return RecurrenceMonthRule(
        month_day=rule.month_day,
        week_of_month=rule.week_of_month,
        weekday=rule.weekday,
        business_day_policy=rule.business_day_policy,
    )
