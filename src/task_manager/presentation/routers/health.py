from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from presentation.dependencies import get_application_readiness
from presentation.schemas.health import HealthResponse, HealthStatus


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=HealthResponse)
async def get_liveness() -> HealthResponse:
    return HealthResponse(status=HealthStatus.OK)


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def get_readiness(
    response: Response,
    is_ready: Annotated[bool, Depends(get_application_readiness)],
) -> HealthResponse:
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status=HealthStatus.UNAVAILABLE)
    return HealthResponse(status=HealthStatus.OK)
