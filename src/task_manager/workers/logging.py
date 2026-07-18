import logging
from logging import getLogger
from typing import Any

from celery.signals import setup_logging, worker_ready, worker_shutdown

from logging_config import configure_logging


logger = getLogger(__name__)


def register_worker_signal_handlers() -> None:
    """Register process logging and lifecycle events without business behavior."""
    setup_logging.connect(
        _configure_worker_logging,
        weak=False,
        dispatch_uid="task-manager-worker-logging",
    )
    worker_ready.connect(
        _log_worker_ready,
        weak=False,
        dispatch_uid="task-manager-worker-ready",
    )
    worker_shutdown.connect(
        _log_worker_shutdown,
        weak=False,
        dispatch_uid="task-manager-worker-shutdown",
    )


def _configure_worker_logging(loglevel: int | None = None, **_: Any) -> None:
    configure_logging(loglevel or logging.INFO)


def _log_worker_ready(sender: Any = None, **_: Any) -> None:
    hostname = getattr(sender, "hostname", None)
    logger.info(
        "event=background_worker_ready hostname=%s outcome=success",
        hostname,
        extra={
            "event": "background_worker_ready",
            "hostname": hostname,
            "outcome": "success",
        },
    )


def _log_worker_shutdown(sender: Any = None, **_: Any) -> None:
    hostname = getattr(sender, "hostname", None)
    logger.info(
        "event=background_worker_shutdown hostname=%s outcome=success",
        hostname,
        extra={
            "event": "background_worker_shutdown",
            "hostname": hostname,
            "outcome": "success",
        },
    )
