from __future__ import annotations

"""Lightweight OpenTelemetry helpers with safe fallbacks.

This module avoids import-time failures when opentelemetry isn't installed.
Use start_span("name") as a context manager and set attributes on the span.
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator


try:  # optional dependency
    from opentelemetry import trace as _trace  # type: ignore
    from opentelemetry.trace import Status, StatusCode  # type: ignore
except Exception:  # pragma: no cover - fall back to no-ops
    _trace = None  # type: ignore
    Status = None  # type: ignore
    StatusCode = None  # type: ignore


def get_tracer(name: str = "gesahni"):
    if _trace is None:  # pragma: no cover - soft fallback
        return None
    return _trace.get_tracer(name)


def init_tracing() -> bool:
    """Best-effort OpenTelemetry SDK initialization.

    - Respects OTEL_ENABLED env (defaults to true)
    - Configures a global TracerProvider with OTLP gRPC exporter if available
    - Sets a minimal Resource with service attributes

    Returns True if tracing was initialized, else False.
    """
    try:
        import os

        enabled = os.getenv("OTEL_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return False
        if _trace is None:
            return False

        # Avoid reinitialization if a provider is already set
        if getattr(_trace, "get_tracer_provider", None) and getattr(_trace.get_tracer_provider(), "_configured", False):
            return True

        # Lazy import SDK bits; guarded to avoid hard dependency in minimal envs
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )

        service_name = os.getenv("OTEL_SERVICE_NAME", "gesahni")
        service_version = os.getenv("OTEL_SERVICE_VERSION", "0")
        resource = Resource.create({SERVICE_NAME: service_name, SERVICE_VERSION: service_version})

        provider = TracerProvider(resource=resource)
        # mark configured to avoid double init
        setattr(provider, "_configured", True)

        # Exporter endpoint (e.g., http://localhost:4317)
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        kwargs: Dict[str, Any] = {}
        if endpoint:
            kwargs["endpoint"] = endpoint
        try:
            exporter = OTLPSpanExporter(**kwargs)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
        except Exception:
            # Exporter unavailable; proceed with in-memory traces only
            pass

        if getattr(_trace, "set_tracer_provider", None):
            _trace.set_tracer_provider(provider)  # type: ignore
        return True
    except Exception:
        return False


@contextmanager
def start_span(name: str, attributes: Dict[str, Any] | None = None) -> Iterator[Any]:
    tracer = get_tracer()
    if tracer is None:
        yield None
        return
    span = tracer.start_span(name=name)
    try:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(k, v)
                except Exception:  # pragma: no cover - best effort
                    pass
        yield span
    except Exception as e:  # propagate after tagging
        try:
            if hasattr(span, "record_exception"):
                span.record_exception(e)  # type: ignore[attr-defined]
            if Status and StatusCode:
                span.set_status(Status(StatusCode.ERROR))  # type: ignore
        except Exception:
            pass
        raise
    finally:
        try:
            span.end()
        except Exception:  # pragma: no cover
            pass


def set_error(span: Any, exc: BaseException) -> None:
    try:
        if span is None:
            return
        # Record exception and mark error on span in a way that survives older SDKs
        if hasattr(span, "record_exception"):
            span.record_exception(exc)
        # Standard error attributes for filters
        if hasattr(span, "set_attribute"):
            try:
                span.set_attribute("error", True)
            except Exception:
                pass
        if Status and StatusCode and hasattr(span, "set_status"):
            try:
                span.set_status(Status(StatusCode.ERROR))  # type: ignore
            except Exception:
                pass
        span.set_attribute("exception.type", type(exc).__name__)
        span.set_attribute("exception.message", str(exc))
    except Exception:  # pragma: no cover
        pass


def get_trace_id_hex() -> str:
    try:
        if _trace is None:
            return ""
        ctx = _trace.get_current_span().get_span_context()  # type: ignore
        if not getattr(ctx, "is_valid", lambda: False)():
            return ""
        # Convert int trace_id to 32‑hex if necessary
        tid = getattr(ctx, "trace_id", 0)
        if isinstance(tid, int):
            return f"{tid:032x}"
        return str(tid)
    except Exception:  # pragma: no cover
        return ""


def observe_with_exemplar(hist, value: float, *, exemplar_labels: Dict[str, str] | None = None):
    """Attempt to observe a Histogram with exemplars; fall back if unsupported."""
    try:
        if exemplar_labels:
            hist.observe(value, exemplar=exemplar_labels)
        else:
            hist.observe(value)
    except TypeError:
        # Older prometheus_client without exemplar support
        hist.observe(value)
    except Exception:
        hist.observe(value)



def shutdown_tracing(timeout_millis: int = 200) -> None:
    """Best-effort tracing shutdown to avoid noisy atexit KeyboardInterrupts.

    Attempts to quickly stop the batch span processor worker thread. Swallows
    all errors so shutdown never blocks application exit.
    """
    try:
        if _trace is None:  # pragma: no cover - no SDK loaded
            return
        provider = _trace.get_tracer_provider()  # type: ignore[attr-defined]
        # Try to directly shutdown the active span processor with a short timeout
        processor = getattr(provider, "_active_span_processor", None)
        if processor is not None and hasattr(processor, "shutdown"):
            try:
                # Newer SDKs accept timeout in millis
                processor.shutdown(timeout_millis)  # type: ignore[arg-type]
            except TypeError:
                # Older SDKs without timeout parameter
                try:
                    processor.shutdown()
                except Exception:
                    pass
        # Also call provider.shutdown() (idempotent in SDKs); ignore any errors
        if hasattr(provider, "shutdown"):
            try:
                provider.shutdown()  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:  # pragma: no cover - never crash on shutdown
        pass

