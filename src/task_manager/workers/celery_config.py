from typing import Any

from celery.schedules import crontab

from config import CeleryConfig


RECURRENCE_MATERIALIZATION_TASK_NAME = "task_manager.recurrence.materialize_tail"
RECURRENCE_MATERIALIZATION_TASK_MODULE = "workers.tasks.recurrence"
RECURRENCE_MATERIALIZATION_SCHEDULE_NAME = "materialize-recurrence-tail-daily"


def build_celery_config(config: CeleryConfig) -> dict[str, Any]:
    """Build Celery runtime settings from validated application configuration."""
    return {
        "accept_content": ("json",),
        "task_serializer": "json",
        "result_serializer": "json",
        "task_ignore_result": True,
        "task_store_errors_even_if_ignored": False,
        "task_default_queue": config.recurrence_materialization_queue,
        "task_routes": {
            RECURRENCE_MATERIALIZATION_TASK_NAME: {
                "queue": config.recurrence_materialization_queue,
            },
        },
        "beat_schedule": {
            RECURRENCE_MATERIALIZATION_SCHEDULE_NAME: {
                "task": RECURRENCE_MATERIALIZATION_TASK_NAME,
                "schedule": crontab(
                    hour=config.recurrence_materialization_hour,
                    minute=config.recurrence_materialization_minute,
                ),
                "options": {
                    "queue": config.recurrence_materialization_queue,
                    "expires": config.message_expires_seconds,
                },
            },
        },
        "timezone": config.timezone,
        "enable_utc": True,
        "worker_concurrency": config.worker_concurrency,
        "worker_prefetch_multiplier": config.worker_prefetch_multiplier,
        "worker_hijack_root_logger": False,
        "worker_redirect_stdouts": False,
        "broker_connection_retry_on_startup": True,
        "broker_pool_limit": config.broker_pool_limit,
        "broker_transport_options": {
            "global_keyprefix": config.broker_key_prefix,
            "visibility_timeout": config.lease_ttl_seconds,
        },
    }
