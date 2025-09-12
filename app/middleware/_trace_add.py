# app/middleware/_trace_add.py (DEV ONLY)
"""
Dev-only tracer to catch rogue middleware registrations.

This module monkey-patches FastAPI.add_middleware to trace calls
for critical middleware classes. Only activate in dev/ci/test environments.
"""

import sys
import traceback

from fastapi import FastAPI

_orig = FastAPI.add_middleware


def traced_add_middleware(self, middleware_class, *args, **kwargs):
    """Traced version of add_middleware that logs calls to critical middleware."""
    name = getattr(middleware_class, "__name__", str(middleware_class))
    if name in {"MetricsMiddleware", "DeprecationHeaderMiddleware"}:
        stack = "".join(traceback.format_stack(limit=8))
        print(f"\nTRACE add_middleware({name}) from:\n{stack}", file=sys.stderr)
    return _orig(self, middleware_class, *args, **kwargs)


# Monkey patch FastAPI.add_middleware
FastAPI.add_middleware = traced_add_middleware
