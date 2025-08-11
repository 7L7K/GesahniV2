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


