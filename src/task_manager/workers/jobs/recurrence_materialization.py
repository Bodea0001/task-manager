from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from logging import getLogger
from time import perf_counter
from typing import Protocol

from config import RecurrenceConfig
from domain.value_objects.tasks import Schedule
from workers.coordination import (
    BackgroundJobClaimStatus,
    BackgroundJobCoordinator,
    run_with_lease,
)


logger = getLogger(__name__)
RECURRENCE_MATERIALIZATION_JOB_NAME = "recurrence-materialization"


class RecurrenceMaterializationService(Protocol):
    async def materialize_recurrence_instances_for_all_owners(
        self,
        window: Schedule,
    ) -> int:
        """Materialize the recurrence tail and return the processed owner count."""
        ...


class MaterializationJobOutcome(StrEnum):
    SUCCESS = "success"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class MaterializationJobResult:
    outcome: MaterializationJobOutcome
    scheduled_date: str
    starts_at: str
    ends_at: str
    owner_count: int
    skip_reason: str | None = None


class RecurrenceMaterializationJob:
    """Coordinate one idempotent extension of the recurrence materialization horizon."""

    def __init__(
        self,
        service: RecurrenceMaterializationService,
        coordinator: BackgroundJobCoordinator,
        recurrence_config: RecurrenceConfig,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._coordinator = coordinator
        self._recurrence_config = recurrence_config
        self._clock = clock

    async def run(self, run_id: str) -> MaterializationJobResult:
        started_at = perf_counter()
        now = self._clock().replace(microsecond=0)
        horizon_days = max(
            self._recurrence_config.daily_materialization_days,
            self._recurrence_config.weekly_materialization_days,
            self._recurrence_config.monthly_materialization_days,
        )
        window = Schedule(
            starts_at=now,
            ends_at=now + timedelta(days=horizon_days),
        )
        scheduled_date = now.date()

        logger.info(
            "event=background_job_started job_name=%s run_id=%s scheduled_date=%s",
            RECURRENCE_MATERIALIZATION_JOB_NAME,
            run_id,
            scheduled_date,
            extra={
                "event": "background_job_started",
                "job_name": RECURRENCE_MATERIALIZATION_JOB_NAME,
                "run_id": run_id,
                "scheduled_date": scheduled_date.isoformat(),
            },
        )

        try:
            claim = await self._coordinator.claim(
                RECURRENCE_MATERIALIZATION_JOB_NAME,
                scheduled_date,
            )
            if claim.status is not BackgroundJobClaimStatus.ACQUIRED:
                result = MaterializationJobResult(
                    outcome=MaterializationJobOutcome.SKIPPED,
                    scheduled_date=scheduled_date.isoformat(),
                    starts_at=window.starts_at.isoformat(),
                    ends_at=window.ends_at.isoformat(),
                    owner_count=0,
                    skip_reason=claim.status.value,
                )
                self._log_terminal(run_id, started_at, result)
                return result

            if claim.lease is None:
                raise RuntimeError("Acquired background job claim has no lease")

            owner_count = await run_with_lease(
                claim.lease,
                self._service.materialize_recurrence_instances_for_all_owners(window),
            )
            result = MaterializationJobResult(
                outcome=MaterializationJobOutcome.SUCCESS,
                scheduled_date=scheduled_date.isoformat(),
                starts_at=window.starts_at.isoformat(),
                ends_at=window.ends_at.isoformat(),
                owner_count=owner_count,
            )
            self._log_terminal(run_id, started_at, result)
            return result
        except BaseException as exc:
            duration_ms = round((perf_counter() - started_at) * 1_000, 3)
            logger.error(
                "event=background_job_ended job_name=%s run_id=%s outcome=error "
                "duration_ms=%.3f error_type=%s",
                RECURRENCE_MATERIALIZATION_JOB_NAME,
                run_id,
                duration_ms,
                type(exc).__name__,
                extra={
                    "event": "background_job_ended",
                    "job_name": RECURRENCE_MATERIALIZATION_JOB_NAME,
                    "run_id": run_id,
                    "scheduled_date": scheduled_date.isoformat(),
                    "outcome": "error",
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                },
            )
            raise

    @staticmethod
    def _log_terminal(
        run_id: str,
        started_at: float,
        result: MaterializationJobResult,
    ) -> None:
        duration_ms = round((perf_counter() - started_at) * 1_000, 3)
        logger.info(
            "event=background_job_ended job_name=%s run_id=%s outcome=%s "
            "duration_ms=%.3f owner_count=%d skip_reason=%s",
            RECURRENCE_MATERIALIZATION_JOB_NAME,
            run_id,
            result.outcome.value,
            duration_ms,
            result.owner_count,
            result.skip_reason,
            extra={
                "event": "background_job_ended",
                "job_name": RECURRENCE_MATERIALIZATION_JOB_NAME,
                "run_id": run_id,
                "scheduled_date": result.scheduled_date,
                "outcome": result.outcome.value,
                "duration_ms": duration_ms,
                "owner_count": result.owner_count,
                "skip_reason": result.skip_reason,
            },
        )
