"""Middleware utilities for detecting unexpected path rewrites."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


def register_path_mismatch_detector(app: FastAPI) -> None:
    """Attach a lightweight middleware that logs path mismatches.

    The client sets an ``x-requested-path`` header indicating the path it
    intended to call. If the actual path seen by FastAPI differs, we emit a
    structured warning so developers can trace unexpected rewrites or browser
    extension interference.
    """

    @app.middleware("http")
    async def path_mismatch_detector(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        intended = request.headers.get("x-requested-path")
        if intended and intended != request.url.path:
            logger.warning(
                "path_mismatch_detected",
                extra={
                    "event": "path_mismatch",
                    "intended": intended,
                    "actual": request.url.path,
                    "method": request.method,
                    "client_fingerprint": request.headers.get(
                        "x-client-route-fingerprint"
                    ),
                    "user_agent": request.headers.get("user-agent"),
                    "via": request.headers.get("via"),
                    "x_forwarded_for": request.headers.get("x-forwarded-for"),
                    "referer": request.headers.get("referer"),
                },
            )

        return await call_next(request)
