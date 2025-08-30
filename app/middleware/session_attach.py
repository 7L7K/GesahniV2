# app/middleware/session_attach.py
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.deps.user import get_current_user_id
from app.security import _get_request_payload

log = logging.getLogger(__name__)


class SessionAttachMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        user_id: str | None = None
        scopes: list | None = (
            None  # None = unauthenticated, [] = authenticated but no scopes
        )

        try:
            # Try to get user_id using existing logic first
            try:
                # Use resolve_user_id to avoid exceptions propagating in middleware
                from app.deps.user import resolve_user_id

                user_id = resolve_user_id(request=request)
            except Exception:
                user_id = None

            # If that doesn't work, try to extract from JWT directly
            if not user_id or user_id == "anon":
                # Check for Authorization header
                auth_header = request.headers.get("authorization", "")
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

                        payload = jwt_decode(token, key=os.getenv("JWT_SECRET"))
                        user_id = payload.get("sub") or payload.get("uid")
                        if user_id:
                            # Successfully authenticated - normalize scopes
                            raw_scopes = payload.get("scopes")
                            if isinstance(raw_scopes, str):
                                scopes = [
                                    s.strip() for s in raw_scopes.split() if s.strip()
                                ]
                            elif isinstance(raw_scopes, (list, tuple, set)):
                                scopes = list(raw_scopes)
                            else:
                                scopes = []  # authenticated but no scopes
                    except Exception:
                        # Authentication failed - leave scopes as None
                        pass

            # Get scopes from JWT payload if available and not already set
            if user_id and user_id != "anon" and scopes is None:
                payload = _get_request_payload(request)
                if isinstance(payload, dict):
                    raw_scopes = payload.get("scopes")
                    if isinstance(raw_scopes, str):
                        scopes = [s.strip() for s in raw_scopes.split() if s.strip()]
                    elif isinstance(raw_scopes, (list, tuple, set)):
                        scopes = list(raw_scopes)
                    else:
                        scopes = []  # authenticated but no scopes
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
        if user_id and user_id != "anon":
            try:
                payload = _get_request_payload(request)
                if isinstance(payload, dict):
                    request.state.jwt_payload = payload
            except Exception:
                pass

        # Record metrics for authenticated requests
        if user_id and user_id != "anon":
            from app.middleware.rate_limit import _record_request_metrics

            _record_request_metrics(user_id, scopes)

        return await call_next(request)
