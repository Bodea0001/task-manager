from fastapi import APIRouter

from presentation.dependencies import CurrentUserDependency, TaskServiceDependency
from presentation.schemas.schedules import (
    FreeTimeRequest,
    FreeTimeResponse,
    NearestFreeScheduleRequest,
    NearestFreeScheduleResponse,
    ScheduleAvailabilityRequest,
    ScheduleAvailabilityResponse,
)


router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.post("/free-time", response_model=FreeTimeResponse)
async def get_free_time(
    request: FreeTimeRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> FreeTimeResponse:
    windows = await task_service.get_free_time(current_user.user_id, request.to_domain())
    return FreeTimeResponse.from_domain(windows)


@router.post("/availability", response_model=ScheduleAvailabilityResponse)
async def check_schedule_availability(
    request: ScheduleAvailabilityRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> ScheduleAvailabilityResponse:
    availability = await task_service.check_schedule_availability(
        current_user.user_id,
        request.to_domain(),
    )
    return ScheduleAvailabilityResponse.from_domain(availability)


@router.post("/nearest-free", response_model=NearestFreeScheduleResponse)
async def find_nearest_free_schedule(
    request: NearestFreeScheduleRequest,
    current_user: CurrentUserDependency,
    task_service: TaskServiceDependency,
) -> NearestFreeScheduleResponse:
    schedule = await task_service.find_nearest_free_schedule(
        current_user.user_id,
        duration=request.duration(),
        excluded_windows=request.excluded_schedules(),
        search_from=request.search_from,
    )
    return NearestFreeScheduleResponse.from_domain(schedule)
