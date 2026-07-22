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

    # Standard attributes every LogRecord has, regardless of what the caller
    # passed via `extra={...}`. Anything on the record NOT in this set is
    # something a caller deliberately attached (call_id, request_id,
    # duration_ms, etc.) and should be surfaced in the JSON output.
    #
    # Why a denylist instead of Phase 1's original fixed whitelist
    # (call_id/utterance_id/user_id/stage): Phase 3 introduced request_id,
    # duration_ms, status_code, path, method - and every future phase will
    # want its own correlation fields (e.g. Phase 8's speech_service might
    # want model_name, audio_duration_ms). Hardcoding each one here would
    # mean editing shared code every single phase. A denylist of Python's
    # own built-in LogRecord attributes is stable and never needs to change.
    _RESERVED_ATTRS = frozenset(logging.LogRecord(
        "", 0, "", 0, "", (), None
    ).__dict__.keys()) | {"service_name", "message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service_name", "unknown"),
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS:
                log_obj[key] = value

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


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
