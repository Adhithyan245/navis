"""
Structured logging configuration for Navis API.

In development (LOG_FORMAT=text, or default): human-readable output.
In production (LOG_FORMAT=json): JSON-formatted lines parseable by
  log aggregators (Datadog, CloudWatch, GCP Logging, etc.).

Standard log fields used across the codebase:
  agent       — which agent handled the request (explore, taste, ...)
  provider    — which external API was called (google_places, yelp, ...)
  action      — what was requested (search_places, search_jobs, ...)
  outcome     — success | fallback | error
  latency_ms  — round-trip time in milliseconds
  reason      — machine-readable failure cause (missing_api_key, timeout, ...)
  trace_id    — per-request correlation ID (present when trace=true)

Usage:
    from core.logging_config import configure_logging
    configure_logging()   # call once at startup in main.py
"""

import logging
import os
import sys


class _StructuredFormatter(logging.Formatter):
    """
    JSON-line formatter for production log shipping.
    Includes standard Navis fields when present in the LogRecord.
    """

    def format(self, record: logging.LogRecord) -> str:
        import json
        import time

        payload = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Attach structured extras if caller provided them
        for field in ("agent", "provider", "action", "outcome", "latency_ms", "reason", "trace_id"):
            val = getattr(record, field, None)
            if val is not None:
                payload[field] = val

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """
    Set up logging for the Navis API process.

    Args:
        level: Log level string (INFO, DEBUG, WARNING, ERROR).

    Reads:
        LOG_FORMAT env var — "json" for structured output, anything else
        (or absent) for human-readable.
        LOG_LEVEL  env var — overrides the `level` argument.
    """
    effective_level_str = os.getenv("LOG_LEVEL", level).upper()
    effective_level = getattr(logging, effective_level_str, logging.INFO)

    log_format = os.getenv("LOG_FORMAT", "text").lower()

    root = logging.getLogger()
    root.setLevel(effective_level)

    # Remove any handlers already attached (e.g. from uvicorn)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(effective_level)

    if log_format == "json":
        handler.setFormatter(_StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        ))

    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for noisy in ("httpx", "sqlalchemy.engine", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configured: level=%s format=%s", effective_level_str, log_format
    )
