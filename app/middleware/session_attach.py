# app/middleware/session_attach.py
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.security import _get_request_payload

log = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


class SessionAttachMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip preflight
        if request.method == "OPTIONS":
            return await call_next(request)
            
        logger.info(f"🔍 SESSION_ATTACH_START: Processing request", extra={
            "meta": {
                "path": request.url.path,
                "method": request.method,
                "cookies_present": list(request.cookies.keys()),
                "auth_header_present": "authorization" in [h.lower() for h in request.headers.keys()],
                "timestamp": time.time()
            }
        })

        user_id: str | None = None
        scopes: list | None = (
            None  # None = unauthenticated, [] = authenticated but no scopes
        )
        payload: dict | None = None  # JWT payload for scope checking functions

        try:
            # OPTIMIZATION: Only do expensive database operations if we have auth tokens
            has_auth_token = False

            # Check for Authorization header
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                has_auth_token = True

            # Check for auth cookies
            if not has_auth_token and any(
                cookie.startswith(("GSNH_AT=", "GSNH_SESS=", "GSNH_RT="))
                for cookie in request.cookies.keys()
            ):
                has_auth_token = True

            # Only do expensive database operations if we have auth tokens
            if has_auth_token:
                try:
                    # Use resolve_user_id to avoid exceptions propagating in middleware
                    from app.deps.user import resolve_user_id

                    user_id = resolve_user_id(request=request)
                except Exception:
                    user_id = None
            else:
                # No auth tokens present - skip expensive database operations
                user_id = None

            # If that doesn't work, try to extract from JWT directly
            if not user_id or user_id == "anon":
                # Get token from auth sources (reuse the has_auth_token logic)
                token = None

                # Check Authorization header first
                if auth_header.lower().startswith("bearer "):
                    token = auth_header.split(None, 1)[1].strip()
                else:
                    # Check for token in query params (for WebSocket compatibility)
                    from urllib.parse import parse_qs

                    qs = parse_qs(request.url.query or "")
                    token = (qs.get("token") or [None])[0]

                if token:
                    try:
                        import os

                        from app.security import jwt_decode

                        # Use central JWT decoder with issuer/audience/leeway support
                        payload = jwt_decode(token, key=os.getenv("JWT_SECRET"), algorithms=["HS256"])
                        user_id = payload.get("sub") or payload.get("uid")
                        if user_id:
                            # Successfully authenticated - normalize scopes
                            # Check for both "scopes" (plural) and "scope" (singular) for compatibility
                            raw_scopes = payload.get("scopes") or payload.get("scope")
                            log.debug(
                                "session_attach.jwt_decoded",
                                extra={
                                    "user_id": user_id,
                                    "raw_scopes": raw_scopes,
                                    "payload_keys": list(payload.keys()),
                                },
                            )
                            if isinstance(raw_scopes, str):
                                scopes = [
                                    s.strip() for s in raw_scopes.split() if s.strip()
                                ]
                            elif isinstance(raw_scopes, list | tuple | set):
                                scopes = list(raw_scopes)
                            else:
                                scopes = []  # authenticated but no scopes
                                log.debug(
                                    "session_attach.no_scopes_direct",
                                    extra={"raw_scopes": raw_scopes},
                                )
                    except Exception:
                        # Authentication failed - leave scopes as None
                        pass

            # Get scopes from JWT payload if available and not already set
            if user_id and user_id != "anon" and scopes is None:
                payload = _get_request_payload(request)
                if isinstance(payload, dict):
                    # Check for both "scopes" (plural) and "scope" (singular) for compatibility
                    raw_scopes = payload.get("scopes") or payload.get("scope")
                    if isinstance(raw_scopes, str):
                        scopes = [s.strip() for s in raw_scopes.split() if s.strip()]
                    elif isinstance(raw_scopes, list | tuple | set):
                        scopes = list(raw_scopes)
                    else:
                        scopes = []  # authenticated but no scopes
                        log.debug(
                            "session_attach.no_scopes_in_payload",
                            extra={
                                "raw_scopes": raw_scopes,
                                "payload_keys": (
                                    list(payload.keys()) if payload else None
                                ),
                            },
                        )
                else:
                    log.debug("session_attach.no_payload", extra={"user_id": user_id})
        except Exception as e:
            log.debug("session_attach.failed", extra={"error": str(e)})
            # On any error, leave scopes as None (unauthenticated)
            pass

        # Attach to request state for downstream middleware/handlers
        request.state.user_id = user_id
        request.state.scopes = (
            scopes  # None = unauthenticated, [] = authenticated but no scopes
        )

        # Also set the JWT payload if we have it for scope checking functions
        if user_id and user_id != "anon" and payload:
            request.state.jwt_payload = payload

        # Record metrics for authenticated requests
        if user_id and user_id != "anon":
            from app.middleware.rate_limit import _record_request_metrics

            _record_request_metrics(user_id, scopes)

        return await call_next(request)
