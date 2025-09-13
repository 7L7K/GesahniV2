from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from datetime import datetime, timedelta, timezone

try:
    from app.metrics import LEGACY_HITS
except ImportError:
    # Fallback stub if metrics unavailable
    class _LegacyHitsStub:
        def labels(self, *args, **kwargs):
            return self
        def inc(self, *args, **kwargs):
            pass
    LEGACY_HITS = _LegacyHitsStub()

class LegacyHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, prefix="/v1/legacy", deprecates_in_days=90):
        super().__init__(app)
        self.prefix = prefix
        self.sunset = (datetime.now(timezone.utc) + timedelta(days=deprecates_in_days)).strftime("%a, %d %b %Y %H:%M:%S GMT")

    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith(self.prefix):
            # Track legacy endpoint usage
            LEGACY_HITS.labels(endpoint=request.url.path).inc()

            # Add deprecation headers
            resp.headers.setdefault("Deprecation", "true")
            resp.headers.setdefault("Sunset", self.sunset)
            resp.headers.setdefault("Link", '</docs#legacy>; rel="deprecation"')
        return resp
