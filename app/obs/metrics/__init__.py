"""Metrics placeholders for Granny Mode."""


def record_p95(stage: str, value_ms: float) -> None:
    _ = (stage, value_ms)


def inc_error(name: str) -> None:
    _ = name

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

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


