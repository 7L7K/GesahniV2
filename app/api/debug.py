import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Admin"])


def _is_dev():
    return os.getenv("ENV", "dev").lower() in {"dev", "local"} or os.getenv(
        "DEV_MODE", "0"
    ).lower() in {"1", "true", "yes", "on"}


@router.get("/debug/config", include_in_schema=False)
async def debug_config():
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")
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
        raise HTTPException(status_code=403, detail="forbidden")

    from ..auth_store_tokens import get_token_system_health
    return await get_token_system_health()


@router.get("/docs/ws", include_in_schema=False)
async def ws_helper_page():
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")
    # Reuse your existing HTML page (shortened here)
    html = "<html><body><h1>WS Helper</h1></body></html>"
    return HTMLResponse(content=html, media_type="text/html")


@router.get("/debug/oauth/routes")
async def debug_oauth_routes(request):
    """List relevant OAuth/Google routes currently registered.

    Makes route visibility obvious during troubleshooting.
    """
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")

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
            "has_login_url": has("/v1/google/auth/login_url") or has("/google/auth/login_url"),
            "has_callback": has("/v1/google/auth/callback") or has("/google/auth/callback"),
            "has_v1_integrations_google_status": has("/v1/integrations/google/status"),
            "has_v1_integrations_google_disconnect": has("/v1/integrations/google/disconnect"),
            "all_oauth_paths": sorted(paths),
        }
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"debug_oauth_routes_failed: {e}")


@router.get("/debug/oauth/config")
async def debug_oauth_config(request):
    """Show effective Google OAuth environment/config in one place."""
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")

    cfg = {
        "GOOGLE_CLIENT_ID_present": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "GOOGLE_CLIENT_SECRET_present": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        "GOOGLE_REDIRECT_URI": os.getenv("GOOGLE_REDIRECT_URI"),
        "JWT_STATE_SECRET_present": bool(os.getenv("JWT_STATE_SECRET")),
        "APP_URL": os.getenv("APP_URL"),
        "FRONTEND_URL": os.getenv("FRONTEND_URL"),
        "NEXT_PUBLIC_API_ORIGIN": os.getenv("NEXT_PUBLIC_API_ORIGIN"),
        "allowed_origins": getattr(getattr(request.app, "state", object()), "allowed_origins", []),
    }

    return cfg


@router.get("/_diag/auth", include_in_schema=False)
async def diag_auth(request: Request):
    """Diagnostic endpoint for authentication state and cookies."""
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")

    from ..web.cookies import read_access_cookie, read_refresh_cookie, read_session_cookie

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
        raise HTTPException(status_code=403, detail="forbidden")
    return {"cookie_names": sorted(request.cookies.keys())}


@router.get("/auth-state", include_in_schema=False)
async def auth_state(request: Request):
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")
    authz = "authorization" in (k.lower() for k in request.headers.keys())
    return {"authz_header_present": authz, "cookie_names": sorted(request.cookies.keys())}


@router.get("/debug/oauth", include_in_schema=False)
async def debug_oauth_page(request):
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")

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
