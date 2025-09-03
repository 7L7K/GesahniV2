from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class AutoOptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            # Build CORS headers using configured helpers if available.
            try:
                from ..settings_cors import (
                    get_cors_allow_methods,
                    get_cors_allow_headers,
                    get_cors_allow_credentials,
                    get_cors_expose_headers,
                    get_cors_max_age,
                )

                origin = request.headers.get("origin") or "*"
                headers = {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": ",".join(get_cors_allow_methods()),
                    "Access-Control-Allow-Headers": ",".join(get_cors_allow_headers()),
                    "Access-Control-Allow-Credentials": "true" if get_cors_allow_credentials() else "false",
                    "Access-Control-Expose-Headers": ",".join(get_cors_expose_headers()),
                    "Access-Control-Max-Age": str(get_cors_max_age()),
                    "Vary": "Origin",
                }
            except Exception:
                # Fallback: minimal permissive preflight headers
                origin = request.headers.get("origin") or "*"
                headers = {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "true",
                    "Vary": "Origin",
                }

            return Response(status_code=204, headers=headers)
        return await call_next(request)


