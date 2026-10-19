"""
observability/opentelemetry.py

OpenTelemetry distributed tracing setup for Navis.
Provides span helpers for the full request lifecycle:
  request → route → orchestrator → provider → fusion → stream → client

Uses OTLP exporter (stdout/OTEL collector). Falls back to NoopTracer
if opentelemetry packages are missing so the server never crashes
on import.
"""
from __future__ import annotations

import asyncio
import functools
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.propagate import inject, extract
    from opentelemetry.trace import SpanKind, Status, StatusCode

    _provider = TracerProvider(
        resource=Resource.create({"service.name": "navis-orchestrator"})
    )
    _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("navis")
    OTEL_AVAILABLE = True

except ImportError:
    OTEL_AVAILABLE = False
    _tracer = None  # type: ignore

from apps.api.core.logging import get_logger

logger = get_logger(__name__)


def get_tracer():
    return _tracer


def start_span(name: str, kind: str = "internal", attributes: Optional[dict] = None):
    """Start a named OTel span. Returns a no-op context manager if OTel unavailable."""
    if not OTEL_AVAILABLE or _tracer is None:
        from contextlib import nullcontext
        return nullcontext()

    from opentelemetry.trace import SpanKind as SK
    kind_map = {
        "server": SK.SERVER,
        "client": SK.CLIENT,
        "producer": SK.PRODUCER,
        "consumer": SK.CONSUMER,
        "internal": SK.INTERNAL,
    }
    return _tracer.start_as_current_span(
        name,
        kind=kind_map.get(kind, SK.INTERNAL),
        attributes=attributes or {},
    )


def trace_async(span_name: str, attributes: Optional[dict] = None):
    """Decorator: wraps an async function in an OTel span."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            with start_span(span_name, attributes=attributes):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


def record_error(span: Any, exc: Exception) -> None:
    """Attach exception info to a span."""
    if not OTEL_AVAILABLE or span is None:
        return
    try:
        from opentelemetry.trace import StatusCode
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:
        pass


def record_cancellation(span: Any) -> None:
    """Mark a span as cancelled."""
    if not OTEL_AVAILABLE or span is None:
        return
    try:
        from opentelemetry.trace import StatusCode
        span.set_attribute("navis.cancelled", True)
        span.set_status(Status(StatusCode.ERROR, "CancelledError"))
    except Exception:
        pass
