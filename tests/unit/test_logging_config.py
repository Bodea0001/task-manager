import json
import logging

from logging_config import JSONLogFormatter


def test_json_log_formatter_preserves_structured_application_fields() -> None:
    record = logging.LogRecord(
        name="presentation.request",
        level=logging.INFO,
        pathname="/application/request_logging.py",
        lineno=42,
        msg="event=%s outcome=%s",
        args=("http_request_completed", "success"),
        exc_info=None,
    )
    record.event = "http_request_completed"
    record.request_id = "request-123"
    record.user_id = None
    record.status_code = 200
    record.duration_ms = 3.0902239959686995
    record.outcome = "success"
    record.validation_errors = ({"location": "body.email", "code": "invalid_value"},)

    payload = json.loads(JSONLogFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "presentation.request"
    assert "message" not in payload
    assert payload["event"] == "http_request_completed"
    assert payload["request_id"] == "request-123"
    assert payload["user_id"] is None
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 3.0902239959686995
    assert payload["outcome"] == "success"
    assert payload["validation_errors"] == [{"location": "body.email", "code": "invalid_value"}]


def test_json_log_formatter_keeps_unstructured_messages() -> None:
    record = logging.LogRecord(
        name="agents.app",
        level=logging.INFO,
        pathname="/application/agents/app.py",
        lineno=65,
        msg="Initializing AgentApplication",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JSONLogFormatter().format(record))

    assert payload["message"] == "Initializing AgentApplication"
    assert "event" not in payload
