from celery import Celery

from config import CeleryConfig, KeyValueStoreConfig, settings
from workers.celery_config import (
    RECURRENCE_MATERIALIZATION_TASK_MODULE,
    build_celery_config,
)
from workers.logging import register_worker_signal_handlers


def create_celery_app(
    config: CeleryConfig,
    key_value_store_config: KeyValueStoreConfig,
) -> Celery:
    """Create the background worker application for CLI discovery or tests."""
    app = Celery(
        "task_manager",
        broker=key_value_store_config.url,
        backend=config.result_backend,
        include=(RECURRENCE_MATERIALIZATION_TASK_MODULE,),
        set_as_current=False,
    )
    app.conf.update(build_celery_config(config))
    register_worker_signal_handlers()
    return app


celery_app = create_celery_app(settings.celery, settings.key_value_store)
