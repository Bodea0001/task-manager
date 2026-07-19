from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import NaiveDatetime

from presentation.dependencies import (
    CurrentUserDependency,
    TaskServiceDependency,
    require_recurrence_expansion_access,
)
from presentation.schemas.audit import AuditEventListResponse
from presentation.schemas.recurrences import (
    CreateRecurrenceRuleRequest,
    CreateRecurrenceTemplateRequest,
    OccurrenceListResponse,
    OccurrenceResponse,
    OccurrenceWindowQuery,
    OptionalOccurrenceResponse,
    RecurrenceRuleListResponse,
    RecurrenceRuleResponse,
    RecurrenceTemplateListQuery,
    RecurrenceTemplateListResponse,
    RecurrenceTemplateResponse,
    StopRecurrenceRuleRequest,
    UpdateOccurrenceRequest,
    UpdateRecurrenceRuleRequest,
)


router = APIRouter(tags=["Recurring Tasks"])


@router.get("/recurrence-templates", response_model=RecurrenceTemplateListResponse)
async def list_recurrence_templates(
    filters: Annotated[RecurrenceTemplateListQuery, Query()],
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceTemplateListResponse:
    templates = await task_service.get_task_recurrence_templates(
        current_user.user_id,
        filters.to_dto(),
    )
    return RecurrenceTemplateListResponse.from_domain(templates)


@router.post(
    "/recurrence-templates",
    response_model=RecurrenceTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recurrence_expansion_access)],
)
async def create_recurrence_template(
    request: CreateRecurrenceTemplateRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceTemplateResponse:
    template = await task_service.add_task_recurrence_template(
        current_user.user_id,
        request.to_dto(),
    )
    return RecurrenceTemplateResponse.from_domain(template)


@router.get(
    "/recurrence-templates/{template_id}",
    response_model=RecurrenceTemplateResponse,
)
async def get_recurrence_template(
    template_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceTemplateResponse:
    template = await task_service.get_task_recurrence_template(
        current_user.user_id,
        template_id,
    )
    return RecurrenceTemplateResponse.from_domain(template)


@router.delete(
    "/recurrence-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_recurrence_template(
    template_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> Response:
    await task_service.delete_task_recurrence_template(current_user.user_id, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/recurrence-templates/{template_id}/history",
    response_model=AuditEventListResponse,
)
async def get_recurrence_template_history(
    template_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListResponse:
    events = await task_service.get_task_recurrence_template_history(
        current_user.user_id,
        template_id,
        limit,
        offset,
    )
    return AuditEventListResponse.from_domain(events)


@router.put(
    "/recurrence-templates/{template_id}/tags/{tag_id}",
    response_model=RecurrenceTemplateResponse,
)
async def add_tag_to_recurrence_template(
    template_id: UUID,
    tag_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceTemplateResponse:
    template = await task_service.add_tag_to_task_recurrence_template(
        current_user.user_id,
        template_id,
        tag_id,
    )
    return RecurrenceTemplateResponse.from_domain(template)


@router.delete(
    "/recurrence-templates/{template_id}/tags/{tag_id}",
    response_model=RecurrenceTemplateResponse,
)
async def remove_tag_from_recurrence_template(
    template_id: UUID,
    tag_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceTemplateResponse:
    template = await task_service.delete_tag_from_task_recurrence_template(
        current_user.user_id,
        template_id,
        tag_id,
    )
    return RecurrenceTemplateResponse.from_domain(template)


@router.get(
    "/recurrence-templates/{template_id}/rules",
    response_model=RecurrenceRuleListResponse,
)
async def list_recurrence_rules(
    template_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceRuleListResponse:
    rules = await task_service.get_task_recurrence_rules(current_user.user_id, template_id)
    return RecurrenceRuleListResponse.from_domain(rules)


@router.post(
    "/recurrence-templates/{template_id}/rules",
    response_model=RecurrenceRuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recurrence_expansion_access)],
)
async def create_recurrence_rule(
    template_id: UUID,
    request: CreateRecurrenceRuleRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceRuleResponse:
    rule = await task_service.add_task_recurrence_rule(
        current_user.user_id,
        template_id,
        request.to_dto(),
    )
    return RecurrenceRuleResponse.from_domain(rule)


@router.patch(
    "/recurrence-rules/{recurrence_id}",
    response_model=RecurrenceRuleResponse,
    dependencies=[Depends(require_recurrence_expansion_access)],
)
async def update_recurrence_rule(
    recurrence_id: UUID,
    request: UpdateRecurrenceRuleRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceRuleResponse:
    rule = await task_service.update_task_recurrence(
        current_user.user_id,
        recurrence_id,
        request.to_dto(),
    )
    return RecurrenceRuleResponse.from_domain(rule)


@router.post(
    "/recurrence-rules/{recurrence_id}/stop",
    response_model=RecurrenceRuleResponse,
)
async def stop_recurrence_rule(
    recurrence_id: UUID,
    request: StopRecurrenceRuleRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> RecurrenceRuleResponse:
    rule = await task_service.stop_task_recurrence(
        current_user.user_id,
        recurrence_id,
        request.stop_from,
    )
    return RecurrenceRuleResponse.from_domain(rule)


@router.delete(
    "/recurrence-rules/{recurrence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_recurrence_rule(
    recurrence_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> Response:
    await task_service.delete_task_recurrence(current_user.user_id, recurrence_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/recurrence-templates/{template_id}/occurrences",
    response_model=OccurrenceListResponse,
)
async def list_occurrences(
    template_id: UUID,
    window: Annotated[OccurrenceWindowQuery, Query()],
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> OccurrenceListResponse:
    occurrences = await task_service.get_task_occurrences(
        current_user.user_id,
        template_id,
        window.to_domain(),
    )
    return OccurrenceListResponse.from_domain(occurrences)


@router.get(
    "/recurrence-occurrences/by-task/{task_id}",
    response_model=OptionalOccurrenceResponse,
)
async def get_occurrence_by_task(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> OptionalOccurrenceResponse:
    occurrence = await task_service.get_recurrence_instance_by_task_id(
        current_user.user_id,
        task_id,
    )
    return OptionalOccurrenceResponse.from_domain(occurrence)


@router.patch(
    "/recurrence-rules/{recurrence_id}/occurrences/{original_starts_at}",
    response_model=OccurrenceResponse,
)
async def update_occurrence(
    recurrence_id: UUID,
    original_starts_at: NaiveDatetime,
    request: UpdateOccurrenceRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> OccurrenceResponse:
    occurrence = await task_service.update_task_occurrence(
        current_user.user_id,
        recurrence_id,
        original_starts_at,
        request.to_dto(),
    )
    return OccurrenceResponse.from_domain(occurrence)


@router.post(
    "/recurrence-rules/{recurrence_id}/occurrences/{original_starts_at}/skip",
    response_model=OccurrenceResponse,
)
async def skip_occurrence(
    recurrence_id: UUID,
    original_starts_at: NaiveDatetime,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> OccurrenceResponse:
    occurrence = await task_service.skip_task_occurrence(
        current_user.user_id,
        recurrence_id,
        original_starts_at,
    )
    return OccurrenceResponse.from_domain(occurrence)
