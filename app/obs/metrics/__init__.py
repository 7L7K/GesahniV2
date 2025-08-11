from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from app import metrics as m
from app.telemetry import log_record_var


@contextmanager
def stage_timer(endpoint: str, method: str, engine: str = "retrieval") -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        try:
            m.REQUEST_LATENCY.labels(endpoint, method, engine).observe(elapsed)
        except Exception:
            pass
        rec = log_record_var.get()
        if rec is not None:
            rec.latency_ms = int((elapsed) * 1000)


__all__ = ["stage_timer"]


