from __future__ import annotations

import time
import random
from typing import Optional


class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple circuit breaker with jittered backoff.

    Usage:
      cb = CircuitBreaker(key)
      if not cb.allow_request(): raise
      try: ...; cb.record_success()
      except Exception as e: cb.record_failure()
    """

    def __init__(self, key: str, fail_threshold: int = 3, base_backoff: float = 5.0, max_backoff: float = 300.0) -> None:
        self.key = key
        self.fail_threshold = fail_threshold
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._fails = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None

    def allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN:
            return True
        # OPEN
        assert self._opened_at is not None
        elapsed = time.time() - self._opened_at
        backoff = min(self.base_backoff * (2 ** (self._fails - self.fail_threshold)), self.max_backoff)
        # add jitter
        jitter = backoff * (0.1 * (random.random() * 2 - 1))
        allow_after = backoff + jitter
        return elapsed >= allow_after

    def record_success(self) -> None:
        self._fails = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._fails += 1
        if self._fails >= self.fail_threshold:
            # open the circuit
            self._state = CircuitState.OPEN
            self._opened_at = time.time()

    def probe(self) -> None:
        # Called by caller to attempt a half-open probe
        if self._state == CircuitState.OPEN and self.allow_request():
            self._state = CircuitState.HALF_OPEN

    def state(self) -> str:
        return self._state


