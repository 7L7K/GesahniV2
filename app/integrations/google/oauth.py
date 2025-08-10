from __future__ import annotations
import json, time, base64, hmac, hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple, List

from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from .config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    GOOGLE_SCOPES, JWT_STATE_SECRET
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

def create_flow(scopes: Optional[List[str]] = None) -> Flow:
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=scopes or GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

def build_auth_url(user_id: str, scopes: Optional[List[str]] = None) -> Tuple[str, str]:
    flow = create_flow(scopes)
    # Uses PKCE automatically; request offline for refresh_token; force prompt to ensure we get it.
    auth_url, g_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    signed = _sign_state({"uid": user_id, "g": g_state})
    # replace google state with our signed state (flow expects any opaque string)
    if "state=" in auth_url:
        auth_url = auth_url.replace(f"state={g_state}", f"state={signed}")
    return auth_url, signed

def exchange_code(code: str, signed_state: str) -> Credentials:
    # Validate CSRF state we sent earlier
    _ = _verify_state(signed_state)
    flow = create_flow()
    # This fetches token using the PKCE code_verifier managed internally
    flow.fetch_token(code=code)
    return flow.credentials

def refresh_if_needed(creds: Credentials) -> Credentials:
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

def creds_to_record(creds: Credentials) -> dict:
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": " ".join(creds.scopes or []),
        "expiry": datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc),
    }

def record_to_creds(record) -> Credentials:
    return Credentials(
        token=record.access_token,
        refresh_token=record.refresh_token,
        token_uri=record.token_uri,
        client_id=record.client_id,
        client_secret=record.client_secret,
        scopes=record.scopes.split(),
        expiry=record.expiry,
    )
