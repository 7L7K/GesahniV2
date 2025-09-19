import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Admin"])


def _is_dev():
    return os.getenv("ENV", "dev").lower() in {"dev", "local", "test"} or os.getenv(
        "DEV_MODE", "0"
    ).lower() in {"1", "true", "yes", "on"}


@router.get("/debug/config", include_in_schema=False)
async def debug_config():
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )
    import os

    from app.main import allow_credentials, origins

    return {
        "environment": {
            "CORS_ALLOW_ORIGINS": os.getenv("CORS_ALLOW_ORIGINS"),
            "APP_URL": os.getenv("APP_URL"),
            "API_URL": os.getenv("API_URL"),
            "HOST": os.getenv("HOST"),
            "PORT": os.getenv("PORT"),
            "CORS_ALLOW_CREDENTIALS": os.getenv("CORS_ALLOW_CREDENTIALS"),
        },
        "runtime": {
            "cors_origins": origins,
            "allow_credentials": allow_credentials,
            "server_host": os.getenv("HOST", "0.0.0.0"),
            "server_port": os.getenv("PORT", "8000"),
        },
        "frontend": {
            "expected_origin": "http://localhost:3000",
            "next_public_api_origin": os.getenv("NEXT_PUBLIC_API_ORIGIN"),
        },
    }


@router.get("/debug/token-health", include_in_schema=False)
async def token_health():
    """Get comprehensive token system health information."""
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )

    from ..auth_store_tokens import get_token_system_health

    return await get_token_system_health()


@router.get("/docs/ws", include_in_schema=False)
async def ws_helper_page():
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )

    # Full WebSocket helper page implementation
    html = """<!DOCTYPE html>
<html>
<head>
    <title>WS Helper • Granny Mode API</title>
    <style>
        body { font-family: monospace; margin: 20px; }
        input, button { margin: 5px; padding: 5px; }
        #events { border: 1px solid #ccc; height: 300px; overflow-y: scroll; padding: 10px; background: #f9f9f9; }
        .error { color: red; }
        .success { color: green; }
        .info { color: blue; }
    </style>
</head>
<body>
    <h1>WebSocket helper</h1>

    <div>
        <label>WebSocket URL:</label>
        <input type="text" id="url" size="50" value="/v1/ws/care">
    </div>

    <div>
        <label>Token:</label>
        <input type="text" id="token" size="50">
    </div>

    <div>
        <label>Resident ID:</label>
        <input type="text" id="resident" size="20" value="test-resident">
    </div>

    <div>
        <label>Topic:</label>
        <input type="text" id="topic" size="30" value="resident:test-resident">
    </div>

    <div>
        <button id="btnConnect">Connect</button>
        <button id="btnDisconnect">Disconnect</button>
        <button id="btnSubscribe">Subscribe</button>
        <button id="btnPing">Ping</button>
    </div>

    <div id="events"></div>

    <script>
        let ws = null;
        const events = document.getElementById('events');

        function log(message, type = 'info') {
            const div = document.createElement('div');
            div.className = type;
            div.textContent = new Date().toLocaleTimeString() + ': ' + message;
            events.appendChild(div);
            events.scrollTop = events.scrollHeight;
        }

        function getTokenFromUrl() {
            const urlParams = new URLSearchParams(window.location.search);
            return urlParams.get('token');
        }

        function buildWebSocketUrl() {
            const baseUrl = document.getElementById('url').value;
            const t = document.getElementById('token').value || getTokenFromUrl();
            if (t) {
                return 'ws://' + window.location.host + baseUrl + '?token=' + encodeURIComponent(t);
            }
            return 'ws://' + window.location.host + baseUrl;
        }

        document.getElementById('btnConnect').onclick = function() {
            if (ws) {
                ws.close();
            }

            const wsUrl = buildWebSocketUrl();
            log('Connecting to: ' + wsUrl);

            try {
                ws = new WebSocket(wsUrl);

                ws.onopen = function() {
                    log('Connected!', 'success');
                };

                ws.onmessage = function(event) {
                    log('Received: ' + event.data, 'info');
                };

                ws.onclose = function() {
                    log('Disconnected', 'error');
                    ws = null;
                };

                ws.onerror = function(error) {
                    log('WebSocket error: ' + error, 'error');
                };
            } catch (e) {
                log('Connection failed: ' + e.message, 'error');
            }
        };

        document.getElementById('btnDisconnect').onclick = function() {
            if (ws) {
                ws.close();
                ws = null;
            }
        };

        document.getElementById('btnSubscribe').onclick = function() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const topic = document.getElementById('topic').value;
                const payload = JSON.stringify({
                    action: 'subscribe',
                    topic: topic
                });
                ws.send(payload);
                log('Sent: ' + payload, 'info');
            } else {
                log('Not connected', 'error');
            }
        };

        document.getElementById('btnPing').onclick = function() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
                log('Sent: ping', 'info');
            } else {
                log('Not connected', 'error');
            }
        };

        // Auto-populate token from URL if present
        window.onload = function() {
            const token = getTokenFromUrl();
            if (token) {
                document.getElementById('token').value = token;
                log('Token loaded from URL', 'success');
            }
        };
    </script>

    <p><strong>Subscribe Payload Hint:</strong> {\\"action\\":\\"subscribe\\",\\"topic\\":\\"resident:{id}\\"}</p>
</body>
</html>"""

    return HTMLResponse(content=html, media_type="text/html")


@router.get("/debug/oauth/routes")
async def debug_oauth_routes(request):
    """List relevant OAuth/Google routes currently registered.

    Makes route visibility obvious during troubleshooting.
    """
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )

    try:
        app = request.app
        paths = []
        for r in getattr(app, "routes", []):
            try:
                p = getattr(r, "path", None)
                if not isinstance(p, str):
                    continue
                if "/google" in p or "/oauth" in p:
                    paths.append(p)
            except Exception:
                continue

        def has(path: str) -> bool:
            return path in paths

        summary = {
            "has_login_url": has("/v1/google/auth/login_url")
            or has("/google/auth/login_url"),
            "has_callback": has("/v1/google/auth/callback")
            or has("/google/auth/callback"),
            "has_v1_integrations_google_status": has("/v1/integrations/google/status"),
            "has_v1_integrations_google_disconnect": has(
                "/v1/integrations/google/disconnect"
            ),
            "all_oauth_paths": sorted(paths),
        }
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"debug_oauth_routes_failed: {e}")


@router.get("/debug/oauth/config")
async def debug_oauth_config(request):
    """Show effective Google OAuth environment/config in one place."""
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )

    cfg = {
        "GOOGLE_CLIENT_ID_present": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "GOOGLE_CLIENT_SECRET_present": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        "GOOGLE_REDIRECT_URI": os.getenv("GOOGLE_REDIRECT_URI"),
        "JWT_STATE_SECRET_present": bool(os.getenv("JWT_STATE_SECRET")),
        "APP_URL": os.getenv("APP_URL"),
        "FRONTEND_URL": os.getenv("FRONTEND_URL"),
        "NEXT_PUBLIC_API_ORIGIN": os.getenv("NEXT_PUBLIC_API_ORIGIN"),
        "allowed_origins": getattr(
            getattr(request.app, "state", object()), "allowed_origins", []
        ),
    }

    return cfg


@router.get("/_diag/auth", include_in_schema=False)
async def diag_auth(request: Request):
    """Diagnostic endpoint for authentication state and cookies."""
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )

    from ..web.cookies import (
        read_access_cookie,
        read_refresh_cookie,
        read_session_cookie,
    )

    return {
        "cookies": {
            "access_token": read_access_cookie(request),
            "refresh_token": read_refresh_cookie(request),
            "session": read_session_cookie(request),
            "csrf_token": request.cookies.get("csrf_token"),
            "all_cookies": dict(request.cookies),
        },
        "headers": {
            "authorization": request.headers.get("authorization"),
            "x-csrf-token": request.headers.get("x-csrf-token"),
            "origin": request.headers.get("origin"),
            "referer": request.headers.get("referer"),
        },
        "user_id": getattr(request.state, "user_id", None),
        "jwt_payload": getattr(request.state, "jwt_payload", None),
    }


# Dev-only lightweight endpoints for auth debugging (names only, no secrets)
@router.get("/cookies", include_in_schema=False)
async def cookies(request: Request):
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )
    return {"cookie_names": sorted(request.cookies.keys())}


@router.get("/auth-state", include_in_schema=False)
async def auth_state(request: Request):
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )
    authz = "authorization" in (k.lower() for k in request.headers.keys())
    return {
        "authz_header_present": authz,
        "cookie_names": sorted(request.cookies.keys()),
    }


@router.get("/debug/oauth", include_in_schema=False)
async def debug_oauth_page(request):
    if not _is_dev():
        from app.http_errors import http_error

        raise http_error(
            code="debug_access_forbidden", message="debug access forbidden", status=403
        )

    # Build a simple HTML that fetches JSON endpoints and renders status lights
    html = """
<!doctype html>
<html><head><meta charset="utf-8"><title>OAuth Debug</title>
<style>
body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:20px}
.ok{color:#065f46;background:#d1fae5;padding:2px 6px;border-radius:4px}
.bad{color:#991b1b;background:#fee2e2;padding:2px 6px;border-radius:4px}
.row{margin:8px 0}
code{background:#f3f4f6;padding:2px 4px;border-radius:4px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
</style></head>
<body>
<h1>OAuth Debug</h1>
<div id="routes" class="row">Loading routes…</div>
<div id="config" class="row">Loading config…</div>
<div id="status" class="row">Loading google status…</div>
<script>
async function load(){
  const a = await fetch('/v1/debug/oauth/routes').then(r=>r.json()).catch(e=>({error:String(e)}));
  const b = await fetch('/v1/debug/oauth/config').then(r=>r.json()).catch(e=>({error:String(e)}));
  const c = await fetch('/v1/integrations/google/status', {credentials:'include'}).then(r=>r.json()).catch(e=>({error:String(e)}));
  const elR = document.getElementById('routes');
  const elC = document.getElementById('config');
  const elS = document.getElementById('status');
  elR.innerHTML = `<h2>Routes</h2>
    <div>login_url: <span class="${a.has_login_url?'ok':'bad'}">${a.has_login_url?'present':'missing'}</span></div>
    <div>callback: <span class="${a.has_callback?'ok':'bad'}">${a.has_callback?'present':'missing'}</span></div>
    <div>v1 integrations google status: <span class="${a.has_v1_integrations_google_status?'ok':'bad'}">${a.has_v1_integrations_google_status?'present':'missing'}</span></div>
    <div>v1 integrations google disconnect: <span class="${a.has_v1_integrations_google_disconnect?'ok':'bad'}">${a.has_v1_integrations_google_disconnect?'present':'missing'}</span></div>
    <details><summary>All paths</summary><div class="mono">${(a.all_oauth_paths||[]).join('<br>')}</div></details>`;
  elC.innerHTML = `<h2>Config</h2>
    <div>CLIENT_ID: <span class="${b.GOOGLE_CLIENT_ID_present?'ok':'bad'}">${b.GOOGLE_CLIENT_ID_present?'set':'missing'}</span></div>
    <div>CLIENT_SECRET: <span class="${b.GOOGLE_CLIENT_SECRET_present?'ok':'bad'}">${b.GOOGLE_CLIENT_SECRET_present?'set':'missing'}</span></div>
    <div>JWT_STATE_SECRET: <span class="${b.JWT_STATE_SECRET_present?'ok':'bad'}">${b.JWT_STATE_SECRET_present?'set':'missing'}</span></div>
    <div>REDIRECT_URI: <code>${b.GOOGLE_REDIRECT_URI||'unset'}</code></div>
    <div>APP_URL: <code>${b.APP_URL||'unset'}</code> | FRONTEND_URL: <code>${b.FRONTEND_URL||'unset'}</code></div>
    <details><summary>allowed_origins</summary><div class="mono">${(b.allowed_origins||[]).join('<br>')}</div></details>`;
  elS.innerHTML = `<h2>Status</h2>
    ${c.error?`<div class="bad">${c.error}</div>`:
      `<div>connected: <span class="${c.connected?'ok':'bad'}">${c.connected}</span></div>
       <div>scopes: <div class="mono">${(c.scopes||[]).join(' ')}</div></div>
       <div>expires_at: <code>${c.expires_at||'n/a'}</code></div>
       <div>degraded_reason: <code>${c.degraded_reason||'n/a'}</code></div>`}
  `;
}
load();
</script>
</body></html>
"""
    return HTMLResponse(content=html, media_type="text/html")


# Lightweight request echo endpoints for cookie/header/auth inspection
@router.get("/debug/headers", include_in_schema=False)
async def debug_headers(request: Request):
    import logging
    logger = logging.getLogger(__name__)

    logger.info("🔍 DEBUG_HEADERS: Processing headers debug request", extra={
        "meta": {
            "method": request.method,
            "url": str(request.url),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "origin": request.headers.get("origin", "unknown"),
            "referer": request.headers.get("referer", "unknown"),
            "timestamp": request.headers.get("date", "unknown")
        }
    })

    try:
        headers = {str(k).lower(): str(v) for k, v in request.headers.items()}
        logger.info(f"🔍 DEBUG_HEADERS: Successfully parsed {len(headers)} headers", extra={
            "meta": {
                "header_count": len(headers),
                "has_authorization": "authorization" in headers,
                "has_csrf": any(k.startswith("x-csrf") for k in headers),
                "has_cookies": "cookie" in headers,
                "cookie_length": len(headers.get("cookie", ""))
            }
        })
    except Exception as e:
        logger.error(f"🔍 DEBUG_HEADERS: Failed to parse headers: {e}", extra={
            "meta": {"error": str(e), "error_type": type(e).__name__}
        })
        headers = {}

    client = None
    try:
        client = request.client.host if request.client else None
        logger.info(f"🔍 DEBUG_HEADERS: Client info: {client}", extra={
            "meta": {"client_host": client, "client_port": getattr(request.client, 'port', None) if request.client else None}
        })
    except Exception as e:
        logger.error(f"🔍 DEBUG_HEADERS: Failed to get client info: {e}", extra={
            "meta": {"error": str(e), "error_type": type(e).__name__}
        })
        client = None

    result = {
        "method": request.method,
        "url": str(request.url),
        "client": client,
        "headers": headers,
        "debug_info": {
            "parsed_successfully": len(headers) > 0,
            "client_info_available": client is not None,
            "request_id": getattr(request.state, 'request_id', None) if hasattr(request, 'state') else None
        }
    }

    logger.info("🔍 DEBUG_HEADERS: Returning result", extra={
        "meta": {
            "result_keys": list(result.keys()),
            "has_debug_info": "debug_info" in result
        }
    })

    return result


@router.get("/debug/cookies", include_in_schema=False)
async def debug_cookies_full(request: Request):
    import logging
    logger = logging.getLogger(__name__)

    logger.info("🍪 DEBUG_COOKIES: Processing cookies debug request", extra={
        "meta": {
            "method": request.method,
            "url": str(request.url),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "origin": request.headers.get("origin", "unknown")
        }
    })

    raw_cookie = ""
    try:
        raw_cookie = request.headers.get("cookie", "")
        logger.info(f"🍪 DEBUG_COOKIES: Raw cookie header length: {len(raw_cookie)}", extra={
            "meta": {
                "has_cookie_header": len(raw_cookie) > 0,
                "cookie_header_length": len(raw_cookie),
                "cookie_header_preview": raw_cookie[:200] + "..." if len(raw_cookie) > 200 else raw_cookie
            }
        })
    except Exception as e:
        logger.error(f"🍪 DEBUG_COOKIES: Failed to get raw cookie header: {e}", extra={
            "meta": {"error": str(e), "error_type": type(e).__name__}
        })
        raw_cookie = ""

    parsed = {}
    try:
        parsed = dict(request.cookies)
        logger.info(f"🍪 DEBUG_COOKIES: Successfully parsed {len(parsed)} cookies", extra={
            "meta": {
                "cookie_names": list(parsed.keys()),
                "has_access_token": "GSNH_AT" in parsed,
                "has_refresh_token": "GSNH_RT" in parsed,
                "has_session": "GSNH_SESS" in parsed,
                "has_csrf": "csrf_token" in parsed,
                "has_device_id": "device_id" in parsed,
                "cookie_value_lengths": {k: len(str(v)) for k, v in parsed.items()}
            }
        })
    except Exception as e:
        logger.error(f"🍪 DEBUG_COOKIES: Failed to parse cookies: {e}", extra={
            "meta": {"error": str(e), "error_type": type(e).__name__}
        })
        parsed = {}

    # Include presence map for convenience without exposing values
    presence = {k: ("present" if (v is not None and v != "") else "") for k, v in parsed.items()}

    # Additional debug info
    debug_info = {
        "parsing_successful": len(parsed) > 0,
        "raw_header_present": len(raw_cookie) > 0,
        "parsed_vs_raw_match": len(parsed) > 0 and len(raw_cookie) > 0,
        "auth_cookies_present": any(k in ["GSNH_AT", "GSNH_RT", "GSNH_SESS"] for k in parsed.keys()),
        "csrf_present": "csrf_token" in parsed,
        "total_cookies": len(parsed)
    }

    result = {"raw": raw_cookie, "parsed": parsed, "presence": presence, "debug_info": debug_info}

    logger.info("🍪 DEBUG_COOKIES: Returning result", extra={
        "meta": {
            "result_keys": list(result.keys()),
            "debug_info": debug_info,
            "cookie_summary": {
                "total": len(parsed),
                "auth_cookies": sum(1 for k in parsed.keys() if k in ["GSNH_AT", "GSNH_RT", "GSNH_SESS"]),
                "other_cookies": sum(1 for k in parsed.keys() if k not in ["GSNH_AT", "GSNH_RT", "GSNH_SESS"])
            }
        }
    })

    return result


@router.get("/debug/whoami/full", include_in_schema=False)
async def debug_whoami_full(request: Request):
    import logging
    logger = logging.getLogger(__name__)

    logger.info("👤 DEBUG_WHOAMI_FULL: Processing full whoami debug request", extra={
        "meta": {
            "method": request.method,
            "url": str(request.url),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "origin": request.headers.get("origin", "unknown"),
            "has_authorization": bool(request.headers.get("authorization")),
            "has_cookie_header": bool(request.headers.get("cookie"))
        }
    })

    # Resolve a best-effort user id without raising on unauthenticated
    user_id = None
    auth_error = None
    try:
        from app.deps.user import resolve_user_id
        logger.info("👤 DEBUG_WHOAMI_FULL: Attempting to resolve user ID", extra={
            "meta": {"attempting_resolution": True}
        })

        user_id = await resolve_user_id(request=request)
        logger.info(f"👤 DEBUG_WHOAMI_FULL: User ID resolution result: {user_id}", extra={
            "meta": {
                "resolved_user_id": user_id,
                "is_authenticated": bool(user_id and user_id != "anon"),
                "is_anonymous": user_id == "anon" or user_id is None
            }
        })
    except Exception as e:
        auth_error = str(e)
        user_id = "anon"
        logger.error(f"👤 DEBUG_WHOAMI_FULL: User ID resolution failed: {e}", extra={
            "meta": {
                "error": str(e),
                "error_type": type(e).__name__,
                "fallback_to_anon": True
            }
        })

    headers = {}
    try:
        headers = {str(k).lower(): str(v) for k, v in request.headers.items()}
        logger.info(f"👤 DEBUG_WHOAMI_FULL: Successfully parsed {len(headers)} headers", extra={
            "meta": {
                "header_count": len(headers),
                "has_authorization": "authorization" in headers,
                "has_csrf": any(k.startswith("x-csrf") for k in headers),
                "has_cookies": "cookie" in headers,
                "has_origin": "origin" in headers,
                "has_user_agent": "user-agent" in headers
            }
        })
    except Exception as e:
        logger.error(f"👤 DEBUG_WHOAMI_FULL: Failed to parse headers: {e}", extra={
            "meta": {"error": str(e), "error_type": type(e).__name__}
        })
        headers = {}

    cookies = {}
    try:
        cookies = dict(request.cookies)
        logger.info(f"👤 DEBUG_WHOAMI_FULL: Successfully parsed {len(cookies)} cookies", extra={
            "meta": {
                "cookie_count": len(cookies),
                "cookie_names": list(cookies.keys()),
                "has_access_token": "GSNH_AT" in cookies,
                "has_refresh_token": "GSNH_RT" in cookies,
                "has_session": "GSNH_SESS" in cookies,
                "has_csrf": "csrf_token" in cookies,
                "has_device_id": "device_id" in cookies
            }
        })
    except Exception as e:
        logger.error(f"👤 DEBUG_WHOAMI_FULL: Failed to parse cookies: {e}", extra={
            "meta": {"error": str(e), "error_type": type(e).__name__}
        })
        cookies = {}

    # Additional debug analysis
    auth_analysis = {
        "is_authenticated": bool(user_id and user_id != "anon"),
        "user_id": user_id if user_id and user_id != "anon" else None,
        "auth_method": "unknown",
        "has_auth_header": "authorization" in headers,
        "has_auth_cookies": any(k in ["GSNH_AT", "GSNH_RT", "GSNH_SESS"] for k in cookies.keys()),
        "has_csrf_token": "csrf_token" in cookies,
        "auth_error": auth_error,
        "resolution_successful": auth_error is None
    }

    # Try to determine auth method
    if "authorization" in headers:
        auth_analysis["auth_method"] = "bearer_token"
    elif any(k in ["GSNH_AT", "GSNH_RT", "GSNH_SESS"] for k in cookies.keys()):
        auth_analysis["auth_method"] = "cookie_auth"
    elif auth_analysis["is_authenticated"]:
        auth_analysis["auth_method"] = "other"
    else:
        auth_analysis["auth_method"] = "none"

    result = {
        "is_authenticated": auth_analysis["is_authenticated"],
        "user": auth_analysis["user_id"],
        "cookies": cookies,
        "headers": headers,
        "auth_analysis": auth_analysis,
        "debug_info": {
            "user_resolution_error": auth_error,
            "headers_parsed": len(headers) > 0,
            "cookies_parsed": len(cookies) > 0,
            "request_id": getattr(request.state, 'request_id', None) if hasattr(request, 'state') else None,
            "timestamp": str(request.headers.get("date", "unknown"))
        }
    }

    logger.info("👤 DEBUG_WHOAMI_FULL: Returning result", extra={
        "meta": {
            "result_keys": list(result.keys()),
            "auth_analysis": auth_analysis,
            "is_authenticated": auth_analysis["is_authenticated"],
            "user_id": auth_analysis["user_id"],
            "auth_method": auth_analysis["auth_method"],
            "has_auth_error": auth_error is not None
        }
    })

    return result
