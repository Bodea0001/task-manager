import json
from typing import Any, NamedTuple
from collections.abc import Awaitable, Callable

from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain.agents.middleware.types import AgentState as LangChainAgentState

import exceptions as app_exc
from agents.schemas.result import AgentResult
from agents.schemas.context import AgentContext


class _ToolErrorDetails(NamedTuple):
    status: str
    code: str
    retryable: bool = False
    resolution: str | None = None


_ERROR_DETAILS: dict[type[app_exc.BaseAppException], _ToolErrorDetails] = {
    app_exc.EmailVerificationRequired: _ToolErrorDetails(
        "forbidden",
        "email_verification_required",
        resolution="Verify the account email in settings, then retry the operation.",
    ),
    app_exc.AgentQuotaExhausted: _ToolErrorDetails(
        "forbidden",
        "agent_quota_exhausted",
    ),
    app_exc.AgentCoordinationUnavailable: _ToolErrorDetails(
        "unavailable",
        "agent_coordination_unavailable",
        True,
    ),
    app_exc.EmailAlreadyExists: _ToolErrorDetails("conflict", "email_already_exists"),
    app_exc.TagAlreadyExists: _ToolErrorDetails("conflict", "tag_already_exists"),
    app_exc.AgentRunInProgress: _ToolErrorDetails("conflict", "agent_run_in_progress"),
    app_exc.ChatNotFound: _ToolErrorDetails("not_found", "chat_not_found"),
    app_exc.TagNotFound: _ToolErrorDetails("not_found", "tag_not_found"),
    app_exc.TaskNotFound: _ToolErrorDetails("not_found", "task_not_found"),
    app_exc.UserNotFound: _ToolErrorDetails("not_found", "user_not_found"),
    app_exc.RecurrenceTemplateNotFound: _ToolErrorDetails(
        "not_found",
        "recurrence_template_not_found",
    ),
    app_exc.RecurrenceRuleNotFound: _ToolErrorDetails(
        "not_found",
        "recurrence_rule_not_found",
    ),
    app_exc.RecurrenceOccurrenceNotFound: _ToolErrorDetails(
        "not_found",
        "recurrence_occurrence_not_found",
    ),
    app_exc.WrongTaskInterval: _ToolErrorDetails(
        "invalid_input",
        "wrong_task_interval",
    ),
    app_exc.TaskScheduleOverlap: _ToolErrorDetails(
        "invalid_input",
        "task_schedule_overlap",
    ),
}


class ApplicationErrorMiddleware(
    AgentMiddleware[LangChainAgentState[AgentResult], AgentContext, AgentResult]
):
    """Expose expected application failures to the model as safe tool results."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except app_exc.BaseAppException as exc:
            return _application_error_message(request, exc)


def _application_error_message(
    request: ToolCallRequest,
    exc: app_exc.BaseAppException,
) -> ToolMessage:
    details = _error_details(exc)
    content = {
        "status": details.status,
        "code": details.code,
        "message": str(exc),
        "retryable": details.retryable,
        "instruction": (
            "Explain this reason to the user and do not claim the operation succeeded. "
            "Return a rejected result unless clarification could resolve the problem."
        ),
    }
    if details.resolution is not None:
        content["resolution"] = details.resolution
    return ToolMessage(
        content=json.dumps(content, ensure_ascii=False, separators=(",", ":")),
        name=request.tool_call["name"],
        tool_call_id=request.tool_call["id"],
        status="error",
    )


def _error_details(exc: app_exc.BaseAppException) -> _ToolErrorDetails:
    if details := _ERROR_DETAILS.get(type(exc)):
        return details
    if isinstance(exc, app_exc.NotFound):
        return _ToolErrorDetails("not_found", "not_found")
    if isinstance(exc, app_exc.Conflict):
        return _ToolErrorDetails("conflict", "conflict")
    if isinstance(exc, app_exc.Forbidden):
        return _ToolErrorDetails("forbidden", "forbidden")
    if isinstance(exc, app_exc.Wrongness):
        return _ToolErrorDetails("invalid_input", "invalid_operation")
    if isinstance(exc, app_exc.Unavailable):
        return _ToolErrorDetails("unavailable", "unavailable", True)
    return _ToolErrorDetails("error", "application_error")
