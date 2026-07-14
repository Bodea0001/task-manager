import json
import logging
from typing import Any
from datetime import UTC, datetime


_STANDARD_LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {"asctime", "message"}


class JSONLogFormatter(logging.Formatter):
    """Serialize application logs and their structured extras as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "process_id": record.process,
            "module": record.module,
            "line": record.lineno,
        }
        if "event" not in record.__dict__:
            payload["message"] = record.getMessage()
        payload.update(
            {
                name: value
                for name, value in record.__dict__.items()
                if name not in _STANDARD_LOG_RECORD_FIELDS and not name.startswith("_")
            }
        )
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


def configure_logging(level: int = logging.INFO) -> None:
    """Configure process-wide JSON logging for application and library records."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,
    )
