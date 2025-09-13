import logging
import re

from fastapi import Request, Response

log = logging.getLogger("auth.debug")
_value_re = re.compile(r"(?:^|;)\s*([^=]+)=([^;]*)")


def redact_cookie_header(set_cookie: str) -> str:
    """Redact the cookie value in a Set-Cookie header while preserving attributes.

    Example input:
        "gs_session=abcdef; Path=/; HttpOnly; Secure; SameSite=Lax"
    Example output:
        "gs_session=«redacted»; Path=/; HttpOnly; Secure; SameSite=Lax"
    """
    parts = set_cookie.split(";")
    if parts:
        try:
            name_val = parts[0].split("=", 1)[0] + "=«redacted»"
            parts[0] = name_val
        except Exception:
            # If anything goes wrong, fall back to a fully redacted token
            return "<set-cookie redacted>"
    return ";".join(p.strip() for p in parts)


def _get_set_cookie_headers(resp: Response) -> list[str]:
    """Return all Set-Cookie header values from a Starlette/FastAPI Response."""
    try:
        # Starlette Headers (request-side) exposes getlist; MutableHeaders may not
        if hasattr(resp.headers, "getlist"):
            return list(resp.headers.getlist("set-cookie"))  # type: ignore[attr-defined]
    except Exception:
        pass
    # Fallback to raw_headers scanning
    try:
        out: list[str] = []
        for k, v in resp.raw_headers or []:
            try:
                if k.decode("latin-1").lower() == "set-cookie":
                    out.append(v.decode("latin-1"))
            except Exception:
                continue
        return out
    except Exception:
        return []


def log_set_cookie(resp: Response, route: str, user_id=None):
    """Log the Set-Cookie headers sent in this response (values redacted)."""
    hdrs = _get_set_cookie_headers(resp)
    if not hdrs:
        log.warning("NO_SET_COOKIE_SENT route=%s user_id=%s", route, user_id)
        return
    for h in hdrs:
        log.info(
            "SET_COOKIE_SENT route=%s user_id=%s header=%s",
            route,
            user_id,
            redact_cookie_header(h),
        )


def log_incoming_cookies(req: Request, route: str):
    """Log cookie presence on an incoming request without exposing values."""
    try:
        cookies = {
            k: ("«present»" if (v is not None and v != "") else "")
            for k, v in req.cookies.items()
        }
    except Exception:
        cookies = {}
    log.info("COOKIES_IN route=%s cookies=%s", route, cookies)
