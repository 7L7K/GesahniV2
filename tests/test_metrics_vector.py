import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.metrics import (
    DEPENDENCY_LATENCY_SECONDS,
    EMBEDDING_LATENCY_SECONDS,
    VECTOR_OP_LATENCY_SECONDS,
)


def test_metric_objects_exist():
    # These are either real prometheus metrics or stubs with .name/.value
    for m in (
        DEPENDENCY_LATENCY_SECONDS,
        EMBEDDING_LATENCY_SECONDS,
        VECTOR_OP_LATENCY_SECONDS,
    ):
        assert m is not None
