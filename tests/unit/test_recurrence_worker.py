from datetime import datetime, timedelta

import pytest

from config import RecurrenceConfig
from domain.value_objects.tasks import Schedule
from workers.coordination import (
    BackgroundJobClaim,
    BackgroundJobClaimStatus,
)
from workers.jobs.recurrence_materialization import (
    MaterializationJobOutcome,
    RecurrenceMaterializationJob,
)


class InMemoryJobCoordinator:
    def __init__(self) -> None:
        self.active = False
        self.completed = False
        self.lease = InMemoryJobLease(self)

    async def claim(self, job_name, scheduled_date) -> BackgroundJobClaim:
        if self.completed:
            return BackgroundJobClaim(BackgroundJobClaimStatus.ALREADY_COMPLETED)
        if self.active:
            return BackgroundJobClaim(BackgroundJobClaimStatus.ALREADY_RUNNING)
        self.active = True
        return BackgroundJobClaim(BackgroundJobClaimStatus.ACQUIRED, self.lease)


class InMemoryJobLease:
    def __init__(self, coordinator: InMemoryJobCoordinator) -> None:
        self._coordinator = coordinator
        self.completed = False
        self.released = False

    @property
    def renew_interval_seconds(self) -> float:
        return 60.0

    async def renew(self) -> bool:
        return self._coordinator.active

    async def complete(self) -> None:
        self.completed = True
        self._coordinator.completed = True
        self._coordinator.active = False

    async def release(self) -> None:
        self.released = True
        self._coordinator.active = False


class RecordingMaterializationService:
    def __init__(self, *, owner_count: int = 3, error: Exception | None = None) -> None:
        self.owner_count = owner_count
        self.error = error
        self.windows: list[Schedule] = []

    async def materialize_recurrence_instances_for_all_owners(
        self,
        window: Schedule,
    ) -> int:
        self.windows.append(window)
        if self.error is not None:
            raise self.error
        return self.owner_count


@pytest.mark.asyncio
async def test_daily_materialization_completes_once_and_skips_a_repeated_run() -> None:
    now = datetime(2099, 1, 1, 12, 30, 15, 123456)
    recurrence_config = RecurrenceConfig(
        daily_materialization_days=30,
        weekly_materialization_days=90,
        monthly_materialization_days=365,
    )
    coordinator = InMemoryJobCoordinator()
    service = RecordingMaterializationService()
    job = RecurrenceMaterializationJob(service, coordinator, recurrence_config, lambda: now)

    first_result = await job.run("first-run")
    repeated_result = await job.run("repeated-run")

    expected_start = now.replace(microsecond=0)
    assert service.windows == [
        Schedule(
            starts_at=expected_start,
            ends_at=expected_start + timedelta(days=365),
        )
    ]
    assert first_result.outcome is MaterializationJobOutcome.SUCCESS
    assert first_result.owner_count == 3
    assert repeated_result.outcome is MaterializationJobOutcome.SKIPPED
    assert repeated_result.skip_reason == BackgroundJobClaimStatus.ALREADY_COMPLETED.value
    assert coordinator.lease.completed


@pytest.mark.asyncio
async def test_failed_materialization_releases_ownership_without_marking_completion() -> None:
    expected_error = RuntimeError("database unavailable")
    coordinator = InMemoryJobCoordinator()
    service = RecordingMaterializationService(error=expected_error)
    job = RecurrenceMaterializationJob(
        service,
        coordinator,
        RecurrenceConfig(),
        lambda: datetime(2099, 1, 1, 12, 0),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await job.run("failed-run")

    assert coordinator.lease.released
    assert not coordinator.completed
    replacement_claim = await coordinator.claim("recurrence-materialization", datetime.now().date())
    assert replacement_claim.status is BackgroundJobClaimStatus.ACQUIRED
