from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from presentation.dependencies import CurrentUserDependency, TaskServiceDependency
from presentation.schemas.audit import AuditEventListResponse
from presentation.schemas.tasks import (
    CreateTaskRequest,
    TaskListQuery,
    TaskListResponse,
    TaskResponse,
    UpdateTaskRequest,
)


router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    filters: Annotated[TaskListQuery, Query()],
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskListResponse:
    result = await task_service.get_tasks(current_user.user_id, filters.to_dto())
    return TaskListResponse.from_domain(result.tasks, result.conflicts)


@router.get("/overdue", response_model=TaskListResponse)
async def list_overdue_tasks(
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListResponse:
    tasks = await task_service.get_overdue_tasks(current_user.user_id, limit, offset)
    return TaskListResponse.from_domain(tasks)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: CreateTaskRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.create_task(current_user.user_id, request.to_dto())
    return TaskResponse.from_domain(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.get_task(current_user.user_id, task_id)
    return TaskResponse.from_domain(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    request: UpdateTaskRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.update_task(current_user.user_id, task_id, request.to_dto())
    return TaskResponse.from_domain(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> Response:
    await task_service.delete_task(current_user.user_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.complete_task(current_user.user_id, task_id)
    return TaskResponse.from_domain(task)


@router.post("/{task_id}/reopen", response_model=TaskResponse)
async def reopen_task(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.reopen_task(current_user.user_id, task_id)
    return TaskResponse.from_domain(task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.cancel_task(current_user.user_id, task_id)
    return TaskResponse.from_domain(task)


@router.delete("/{task_id}/schedule", response_model=TaskResponse)
async def delete_task_schedule(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.delete_schedule_from_task(current_user.user_id, task_id)
    return TaskResponse.from_domain(task)


@router.put("/{task_id}/tags/{tag_id}", response_model=TaskResponse)
async def add_tag_to_task(
    task_id: UUID,
    tag_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.add_tag_to_task(current_user.user_id, task_id, tag_id)
    return TaskResponse.from_domain(task)


@router.delete("/{task_id}/tags/{tag_id}", response_model=TaskResponse)
async def remove_tag_from_task(
    task_id: UUID,
    tag_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> TaskResponse:
    task = await task_service.delete_tag_from_task(current_user.user_id, task_id, tag_id)
    return TaskResponse.from_domain(task)


@router.get("/{task_id}/history", response_model=AuditEventListResponse)
async def get_task_history(
    task_id: UUID,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListResponse:
    events = await task_service.get_task_history(current_user.user_id, task_id, limit, offset)
    return AuditEventListResponse.from_domain(events)
