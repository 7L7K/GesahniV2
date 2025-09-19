import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REDACT = "■" * 8


def _summarize_set_cookie(headers):
    # returns e.g. ["GSNH_AT; HttpOnly; Path=/; SameSite=Lax; Secure=absent; Domain=absent", ...]
    items = []
    for k, v in headers:
        # raw headers may be bytes
        key = k.decode() if isinstance(k, bytes | bytearray) else k
        val = v.decode() if isinstance(v, bytes | bytearray) else v
        if key.lower() == "set-cookie":
            name = val.split("=", 1)[0]
            flags = {
                "HttpOnly": "HttpOnly" in val,
                "Secure": "Secure" in val,
                "SameSite": (
                    "SameSite="
                    + (
                        val.split("SameSite=")[1].split(";")[0]
                        if "SameSite=" in val
                        else "absent"
                    )
                ),
                "Path": (
                    "Path="
                    + (
                        val.split("Path=")[1].split(";")[0]
                        if "Path=" in val
                        else "absent"
                    )
                ),
                "Domain": (
                    "Domain="
                    + (
                        val.split("Domain=")[1].split(";")[0]
                        if "Domain=" in val
                        else "absent"
                    )
                ),
            }
            items.append(
                f"{name}; "
                f"{'HttpOnly' if flags['HttpOnly'] else 'HttpOnly=absent'}; "
                f"{flags['Path']}; {flags['SameSite']}; "
                f"{'Secure' if flags['Secure'] else 'Secure=absent'}; "
                f"{flags['Domain']}"
            )
    return items


class AuthDiagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-req-id") or str(uuid.uuid4())
        # only record cookie *names*, never values
        cookie_names = sorted(request.cookies.keys())
        authz_present = "authorization" in (k.lower() for k in request.headers.keys())
        
        # Enhanced diagnostic information
        auth_cookies = [name for name in cookie_names if any(suffix in name.lower() for suffix in ['_at', '_rt', '_sess', 'access', 'refresh', 'session'])]
        csrf_present = "csrf_token" in cookie_names
        origin = request.headers.get("origin", "none")
        referer = request.headers.get("referer", "none")
        user_agent = request.headers.get("user-agent", "none")[:50] + "..." if len(request.headers.get("user-agent", "")) > 50 else request.headers.get("user-agent", "none")
        
        resp: Response = await call_next(request)

        set_cookie_summaries = _summarize_set_cookie(getattr(resp, "raw_headers", []))

        # Echo enhanced diag for easy inspection
        try:
            resp.headers["X-Req-Id"] = rid
            resp.headers["X-AuthDiag-Req"] = (
                f"cookies={cookie_names}; authz={authz_present}; auth_cookies={auth_cookies}; csrf={csrf_present}"
            )
            if set_cookie_summaries:
                resp.headers["X-AuthDiag-SetCookie"] = " | ".join(
                    set_cookie_summaries[:3]
                )
            
            # Add additional diagnostic headers
            resp.headers["X-AuthDiag-Origin"] = origin
            resp.headers["X-AuthDiag-UserAgent"] = user_agent
            resp.headers["X-AuthDiag-CSRF"] = "present" if csrf_present else "absent"
            resp.headers["X-AuthDiag-AuthCookies"] = ",".join(auth_cookies) if auth_cookies else "none"
        except Exception:
            pass

        # Enhanced structured log line (redacted)
        try:
            logger = getattr(request.app.state, "logger", None)
            log_item = {
                "rid": rid,
                "path": request.url.path,
                "method": request.method,
                "cookies_seen": cookie_names,
                "auth_cookies": auth_cookies,
                "authz_header_present": authz_present,
                "csrf_present": csrf_present,
                "origin": origin,
                "referer": referer,
                "user_agent_length": len(request.headers.get("user-agent", "")),
                "set_cookie": set_cookie_summaries,
            }
            if logger is not None and hasattr(logger, "info"):
                logger.info(log_item)
            else:
                # Fallback to printing to the default logger
                import logging

                logging.getLogger(__name__).info(log_item)
        except Exception:
            pass

        return resp
