import asyncio
from datetime import datetime
from logging import getLogger
from uuid import uuid4
from zoneinfo import ZoneInfo

from celery.app.task import Task
from sqlalchemy.exc import DBAPIError

from config import settings
from workers.app import celery_app
from workers.celery_config import RECURRENCE_MATERIALIZATION_TASK_NAME
from workers.coordination import BackgroundJobCoordinationUnavailable
from workers.jobs.recurrence_materialization import RecurrenceMaterializationJob
from workers.runtime import WorkerRuntime


logger = getLogger(__name__)
_RETRYABLE_SQLSTATES = frozenset(
    {
        "40001",  # serialization_failure
        "40P01",  # deadlock_detected
        "53300",  # too_many_connections
        "57P01",  # admin_shutdown
        "57P02",  # crash_shutdown
        "57P03",  # cannot_connect_now
    }
)


@celery_app.task(
    bind=True,
    name=RECURRENCE_MATERIALIZATION_TASK_NAME,
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
    max_retries=settings.celery.retry_max_retries,
    soft_time_limit=settings.celery.task_soft_time_limit_seconds,
    time_limit=settings.celery.task_time_limit_seconds,
)
def materialize_recurrence_tail(task: Task) -> None:
    run_id = task.request.id or uuid4().hex
    try:
        asyncio.run(_run_materialization(run_id))
    except Exception as exc:
        if not _is_retryable_error(exc):
            raise

        retry_number = task.request.retries + 1
        countdown = min(
            settings.celery.retry_backoff_seconds * (2 ** (retry_number - 1)),
            settings.celery.retry_backoff_max_seconds,
        )
        logger.warning(
            "event=background_job_retry_scheduled job_name=%s run_id=%s retry=%d "
            "countdown_seconds=%d error_type=%s",
            "recurrence-materialization",
            run_id,
            retry_number,
            countdown,
            type(exc).__name__,
            extra={
                "event": "background_job_retry_scheduled",
                "job_name": "recurrence-materialization",
                "run_id": run_id,
                "retry": retry_number,
                "countdown_seconds": countdown,
                "error_type": type(exc).__name__,
            },
        )
        raise task.retry(exc=exc, countdown=countdown) from exc


async def _run_materialization(run_id: str) -> None:
    async with WorkerRuntime(
        settings.db,
        settings.celery,
        settings.key_value_store,
    ) as runtime:
        job = RecurrenceMaterializationJob(
            runtime.task_service,
            runtime.job_coordinator,
            settings.recurrence,
            clock=lambda: datetime.now(ZoneInfo(settings.celery.timezone)).replace(tzinfo=None),
        )
        await job.run(run_id)


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, (BackgroundJobCoordinationUnavailable, ConnectionError, TimeoutError)):
        return True
    if not isinstance(exc, DBAPIError):
        return False
    if exc.connection_invalidated:
        return True

    sqlstate = _find_sqlstate(exc.orig)
    return bool(sqlstate and (sqlstate.startswith("08") or sqlstate in _RETRYABLE_SQLSTATES))


def _find_sqlstate(exc: BaseException | None) -> str | None:
    current: BaseException | None = exc
    while current is not None:
        sqlstate = getattr(current, "sqlstate", None)
        if isinstance(sqlstate, str):
            return sqlstate
        current = current.__cause__ or current.__context__
    return None
