from __future__ import annotations
import json, time, base64, hmac, hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, List, Any

from fastapi import HTTPException

# Optional Google libraries ----------------------------------------------------
try:  # pragma: no cover - import varies by environment
    from google_auth_oauthlib.flow import Flow as _Flow  # type: ignore
    from google.oauth2.credentials import Credentials as _Credentials  # type: ignore
    from google.auth.transport.requests import Request as _Request  # type: ignore
    _GOOGLE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _Flow = None
    _Credentials = None
    _Request = None
    _GOOGLE_AVAILABLE = False

from urllib.parse import urlencode

from .config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    JWT_STATE_SECRET,
    get_google_scopes,
)

CLIENT_CONFIG = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "project_id": "gesahni",  # name is not critical
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uris": [GOOGLE_REDIRECT_URI],
    }
}

def _sign_state(payload: Dict, ttl_sec: int = 600) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_sec
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(JWT_STATE_SECRET.encode(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + b"." + sig).decode()

def _verify_state(state: str) -> Dict:
    try:
        raw = base64.urlsafe_b64decode(state.encode())
        body, sig = raw.rsplit(b".", 1)
        exp_sig = hmac.new(JWT_STATE_SECRET.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, exp_sig):
            raise ValueError("bad signature")
        payload = json.loads(body.decode())
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state")

def create_flow(scopes: Optional[List[str]] = None):
    """Return a google-auth ``Flow`` when libraries are available.

    Raises HTTPException when unavailable so callers can degrade gracefully.
    """
    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        raise HTTPException(status_code=501, detail="google oauth client unavailable")
    return _Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=scopes or get_google_scopes(),
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

def build_auth_url(
    user_id: str,
    scopes: Optional[List[str]] = None,
    extra_state: Optional[Dict] = None,
) -> Tuple[str, str]:
    """Return an OAuth authorization URL and our signed state.

    Uses the official Flow when available; otherwise constructs the URL
    manually so tests and lightweight environments work without heavy deps.
    """
    requested_scopes = scopes or get_google_scopes()
    # Compose our signed state first
    state_payload: Dict[str, Any] = {"uid": user_id}
    if extra_state:
        state_payload.update(extra_state)
    signed = _sign_state(state_payload)

    # Always construct the URL manually for deterministic scopes to avoid
    # oauthlib "scope_changed" exceptions due to Google returning userinfo.*
    # even when requesting email/profile.

    # Manual construction fallback
    q = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(requested_scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": signed,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{q}", signed

def exchange_code(code: str, signed_state: str):
    # Validate CSRF state we sent earlier
    _ = _verify_state(signed_state)
    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        # Environments without google libraries should override this function in tests
        raise HTTPException(status_code=501, detail="google oauth exchange unavailable")
    # First try via official client
    try:
        flow = create_flow()
        flow.fetch_token(code=code)
        return flow.credentials
    except Exception:
        # Fallback: manual token exchange to avoid oauthlib scope_changed issues
        try:
            import requests
            from datetime import datetime, timezone, timedelta

            resp = requests.post(
                CLIENT_CONFIG["web"]["token_uri"],
                data={
                    "code": code,
                    "client_id": CLIENT_CONFIG["web"]["client_id"],
                    "client_secret": CLIENT_CONFIG["web"]["client_secret"],
                    "redirect_uri": CLIENT_CONFIG["web"]["redirect_uris"][0],
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            if not resp.ok:
                raise HTTPException(status_code=400, detail="oauth_exchange_failed")
            data = resp.json()

            class _SimpleCreds:
                def __init__(self, d):
                    self.token = d.get("access_token")
                    self.refresh_token = d.get("refresh_token")
                    self.id_token = d.get("id_token")
                    scope_raw = d.get("scope") or " ".join(get_google_scopes())
                    self.scopes = scope_raw.split()
                    expires_in = int(d.get("expires_in") or 3600)
                    self.expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    self.token_uri = CLIENT_CONFIG["web"]["token_uri"]
                    self.client_id = CLIENT_CONFIG["web"]["client_id"]
                    self.client_secret = CLIENT_CONFIG["web"]["client_secret"]

            return _SimpleCreds(data)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"oauth_exchange_failed: {e}")

def refresh_if_needed(creds: Any) -> Any:
    try:
        expired = getattr(creds, "expired", False)
        has_refresh = getattr(creds, "refresh_token", None)
        if expired and has_refresh and _GOOGLE_AVAILABLE and _Request is not None:  # pragma: no cover
            creds.refresh(_Request())
    except Exception:
        pass
    return creds

def creds_to_record(creds: Any) -> dict:
    # Robustly convert creds into a serializable record, tolerating stubs
    try:
        scopes = getattr(creds, "scopes", None) or []
        if isinstance(scopes, str):
            scopes = scopes.split()
        expiry = getattr(creds, "expiry", None)
        if expiry is None:
            expiry_dt = datetime.now(timezone.utc) + timedelta(hours=1)
        elif isinstance(expiry, datetime):
            expiry_dt = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
        else:
            # objects with .timestamp()
            try:
                expiry_dt = datetime.fromtimestamp(expiry.timestamp(), tz=timezone.utc)  # type: ignore[arg-type]
            except Exception:
                expiry_dt = datetime.now(timezone.utc) + timedelta(hours=1)
        return {
            "access_token": getattr(creds, "token", None),
            "refresh_token": getattr(creds, "refresh_token", None),
            "token_uri": getattr(creds, "token_uri", "https://oauth2.googleapis.com/token"),
            "client_id": getattr(creds, "client_id", GOOGLE_CLIENT_ID),
            "client_secret": getattr(creds, "client_secret", GOOGLE_CLIENT_SECRET),
            "scopes": " ".join(scopes),
            "expiry": expiry_dt,
        }
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=f"bad_credentials_object: {e}")

def record_to_creds(record):
    if not _GOOGLE_AVAILABLE or _Credentials is None:  # pragma: no cover - env-dependent
        raise HTTPException(status_code=501, detail="google credentials unavailable")
    return _Credentials(
        token=record.access_token,
        refresh_token=record.refresh_token,
        token_uri=record.token_uri,
        client_id=record.client_id,
        client_secret=record.client_secret,
        scopes=record.scopes.split(),
        expiry=record.expiry,
    )
