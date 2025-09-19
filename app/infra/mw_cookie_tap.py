import uuid, re, logging
from starlette.middleware.base import BaseHTTPMiddleware

SET_COOKIE_RE = re.compile(r"(?i)^set-cookie$")
log = logging.getLogger("cookie.tap")

class CookieTap(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace = request.headers.get("x-trace-id") or str(uuid.uuid4())
        request.state.trace_id = trace
        response = await call_next(request)
        # Grab ALL set-cookie headers
        sc = [v for (k, v) in response.headers.raw if k.decode().lower() == "set-cookie"]
        for i, v in enumerate(sc, 1):
            log.info("[COOKIE][%s] #%d %s %s", trace, i, request.url.path, v)
        # Echo trace id so frontend / curl can correlate
        response.headers["x-trace-id"] = trace
        return response
