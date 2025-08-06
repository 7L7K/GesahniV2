"""Very small stub of NumPy used for tests.

The test-suite only requires :func:`zeros` to produce a matrix of the given
shape.  Implementing the entire library would be unnecessary so this module
provides just enough to satisfy the import.
"""

from typing import Any, List, Tuple


def zeros(shape: Tuple[int, int], dtype: Any | None = None) -> List[List[int]]:
    rows, cols = shape
    return [[0 for _ in range(cols)] for _ in range(rows)]


__all__ = ["zeros"]
