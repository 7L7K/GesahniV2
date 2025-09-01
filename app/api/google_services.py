from __future__ import annotations

import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps.user import get_current_user_id
from ..auth_store_tokens import get_token
from ..service_state import set_status, parse
from ..integrations.google.oauth import gmail_unread_count, calendar_next_event

router = APIRouter(tags=["GoogleServices"])


@router.post("/verify")
async def verify_google_access(request: Request):
    """Ping Gmail and Calendar using stored token and update service_state with last successful ping."""
    user_id = get_current_user_id(request=request)
    if not user_id or user_id == "anon":
        return JSONResponse({"ok": False, "error": "auth_required"}, status_code=401)

    token = await get_token(user_id, "google")
    if not token or not token.access_token:
        return JSONResponse({"ok": False, "error": "no_token"}, status_code=400)

    services = {}
    try:
        unread = await gmail_unread_count(token.access_token)
        services['gmail'] = {'status': 'enabled', 'last_ping': int(time.time()), 'unread': unread}
    except Exception:
        services['gmail'] = {'status': 'error'}

    try:
        evt = await calendar_next_event(token.access_token)
        services['calendar'] = {'status': 'enabled', 'last_ping': int(time.time()), 'next_event': evt}
    except Exception:
        services['calendar'] = {'status': 'error'}

    # Update token service_state (best-effort)
    try:
        st = parse(getattr(token, 'service_state', None))
        for svc, info in services.items():
            if info.get('status') == 'enabled':
                st[svc] = {'status': 'enabled', 'last_changed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'last_ping': info.get('last_ping')}
            else:
                st[svc] = {'status': 'error', 'last_changed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        from ..auth_store_tokens import upsert_token
        token.service_state = __import__('json').dumps(st)
        token.updated_at = int(time.time())
        await upsert_token(token)
    except Exception:
        pass

    return JSONResponse({"ok": True, "services": services})
