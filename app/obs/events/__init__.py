from __future__ import annotations

from typing import Any, Dict

from app.telemetry import log_record_var


def emit(stage: str, **meta: Any) -> None:
    rec = log_record_var.get()
    if rec is None:
        return
    trace = getattr(rec, "route_trace", None) or []
    trace.append({"stage": stage, "meta": meta})
    rec.route_trace = trace


__all__ = ["emit"]


