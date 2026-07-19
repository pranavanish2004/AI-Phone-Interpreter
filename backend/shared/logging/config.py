"""
Centralized logging setup.

Why this matters in a microservices system:
    When a call goes wrong, the failure could be in any of 7 services. If
    each service logs in a different format, correlating "what happened to
    call_id=call_123" across audio_service, speech_service, and
    translation_service logs becomes painful grep-archaeology. This module
    enforces ONE structured JSON log format everywhere, so logs can be
    aggregated (e.g. shipped to a log platform later) and filtered by
    call_id/utterance_id across every service consistently.
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Renders each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service_name", "unknown"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Allow call_id/utterance_id/etc to be attached via `extra={...}`
        # in individual log calls, e.g.:
        #   logger.info("chunk received", extra={"call_id": "call_123"})
        for key in ("call_id", "utterance_id", "user_id", "stage"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def configure_logging(service_name: str, level: int = logging.INFO) -> None:
    """
    Call this ONCE at service startup (in main.py), before any other logging
    happens.

    Args:
        service_name: identifies which microservice emitted the log, e.g.
                       "speech_service" - critical for filtering logs later.
        level: minimum severity to emit; INFO by default, DEBUG in local dev.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    # Inject service_name onto every record automatically so callers don't
    # have to pass extra={"service_name": ...} on every single log line.
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service_name = service_name
        return record

    logging.setLogRecordFactory(record_factory)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]
