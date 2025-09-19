"""Request origin enforcement middleware."""

from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urlparse

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _normalize_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc:
            return None
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        return f"{scheme}://{netloc}"
    except Exception:
        return None


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Block state-changing requests that lack an approved Origin header."""

    def __init__(
        self,
        app,
        *,
        allowed_origins: Iterable[str] | None = None,
        allow_same_origin: bool = True,
    ) -> None:
        super().__init__(app)
        allowed = set()
        for value in allowed_origins or []:
            normalized = _normalize_origin(value)
            if normalized:
                allowed.add(normalized)
        self._allowed = allowed
        self._allow_same_origin = allow_same_origin

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        if method in _STATE_CHANGING_METHODS and self._should_enforce(request):
            origin_header = request.headers.get("origin") or request.headers.get("Origin")
            normalized_origin = _normalize_origin(origin_header)

            if normalized_origin:
                # Explicit Origin provided: must be allowed or same-origin
                if not self._is_allowed(request, normalized_origin):
                    return self._reject(request, "bad_origin")
            else:
                # No Origin header - infer from Referer or scheme+host for dev/proxy tools
                # 1) Try Referer
                referer_header = request.headers.get("referer") or request.headers.get("Referer")
                referer_origin = _normalize_origin(referer_header)
                if referer_origin:
                    if not self._is_allowed(request, referer_origin):
                        return self._reject(request, "bad_origin")
                else:
                    # 2) Build origin from forwarded headers or request URL/Host
                    try:
                        scheme = (
                            (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
                            or (request.url.scheme or "http").lower()
                        )
                        host = (
                            (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
                            or (request.headers.get("host") or "").strip()
                        )
                        inferred = _normalize_origin(f"{scheme}://{host}" if host else None)
                    except Exception:
                        inferred = None

                    # If we can infer and it is not allowed, block; otherwise allow as same-origin fallback
                    if inferred and not self._is_allowed(request, inferred):
                        return self._reject(request, "bad_origin")

        response = await call_next(request)
        self._ensure_vary(response)
        return response

    def _should_enforce(self, request: Request) -> bool:
        cookie_header = request.headers.get("cookie") or request.headers.get("Cookie")
        return bool(cookie_header)

    def _is_allowed(self, request: Request, origin: str) -> bool:
        if origin in self._allowed:
            return True
        if not self._allow_same_origin:
            return False
        try:
            host_header = request.headers.get("host")
            if not host_header:
                return False
            parsed_origin = urlparse(origin)
            request_scheme = request.url.scheme.lower() if request.url.scheme else "http"
            normalized_host = host_header.lower()
            return (
                parsed_origin.scheme.lower() == request_scheme
                and parsed_origin.netloc.lower() == normalized_host
            )
        except Exception:
            return False

    def _reject(self, request: Request, reason: str) -> JSONResponse:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            "origin_guard.blocked",
            extra={
                "meta": {
                    "path": request.url.path,
                    "method": request.method,
                    "reason": reason,
                    "origin": request.headers.get("origin") or "<missing>",
                    "ip": client_ip,
                }
            },
        )
        response = JSONResponse(status_code=403, content={"detail": reason})
        self._ensure_vary(response)
        return response

    @staticmethod
    def _ensure_vary(response: Response) -> None:
        try:
            existing = response.headers.get("Vary")
            if not existing:
                response.headers["Vary"] = "Origin"
                return
            parts = [p.strip() for p in existing.split(",") if p.strip()]
            if "origin" not in {p.lower() for p in parts}:
                parts.append("Origin")
                response.headers["Vary"] = ", ".join(parts)
        except Exception:
            # Header mutations should never raise
            pass


__all__ = ["OriginGuardMiddleware"]
