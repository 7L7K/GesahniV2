from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

# Optional Google libraries ----------------------------------------------------
try:  # pragma: no cover - import varies by environment
    from google.auth.transport.requests import Request as _Request  # type: ignore
    from google.oauth2.credentials import Credentials as _Credentials  # type: ignore
    from google_auth_oauthlib.flow import Flow as _Flow  # type: ignore
    _GOOGLE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _Flow = None
    _Credentials = None
    _Request = None
    _GOOGLE_AVAILABLE = False


from .config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    JWT_STATE_SECRET,
    get_google_scopes,
)

logger = logging.getLogger(__name__)

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

def _b64u_encode(data: bytes) -> str:
    # Return base64url without padding for compact URLs
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64u_decode(data: str) -> bytes:
    # Add padding back if missing
    pad = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode((data + pad).encode())


def _sign_state(payload: dict, ttl_sec: int = 600) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_sec
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(JWT_STATE_SECRET.encode(), raw, hashlib.sha256).digest()
    # Encode body and signature separately to avoid delimiter collisions
    return f"{_b64u_encode(raw)}.{_b64u_encode(sig)}"

def _verify_state(state: str) -> dict:
    # Primary path: split into base64url(body).base64url(sig)
    try:
        if "." in state:
            b64_body, b64_sig = state.split(".", 1)
            body = _b64u_decode(b64_body)
            sig = _b64u_decode(b64_sig)
            exp_sig = hmac.new(JWT_STATE_SECRET.encode(), body, hashlib.sha256).digest()
            if not hmac.compare_digest(sig, exp_sig):
                raise ValueError("bad signature")
            payload = json.loads(body.decode())
            if payload.get("exp", 0) < int(time.time()):
                raise ValueError("expired")
            return payload
    except Exception:
        # Fall through to legacy decode
        pass
    # Legacy fallback: single base64url encoding of body + b'.' + sig
    try:
        raw = base64.urlsafe_b64decode(state.encode())
        # The legacy format concatenated raw JSON, a byte '.', then raw HMAC bytes.
        # Since HMAC bytes may contain '.', split using the known digest size from the end.
        if len(raw) <= 33:  # 1 for '.' + 32 for HMAC-SHA256
            raise ValueError("truncated")
        body, delim, sig = raw[:-33], raw[-33:-32], raw[-32:]
        if delim != b".":
            raise ValueError("bad delimiter")
        exp_sig = hmac.new(JWT_STATE_SECRET.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, exp_sig):
            raise ValueError("bad signature")
        payload = json.loads(body.decode())
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state")

def create_flow(scopes: list[str] | None = None):
    """Return a google-auth ``Flow`` when libraries are available.

    Raises HTTPException when unavailable so callers can degrade gracefully.
    """
    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        raise HTTPException(status_code=503, detail="Google OAuth libraries unavailable")
    return _Flow.from_client_config(CLIENT_CONFIG, scopes=scopes or get_google_scopes())

def build_auth_url(user_id: str, state_payload: dict | None = None) -> tuple[str, str]:
    """Build a Google OAuth URL with optional state payload.

    Returns:
        Tuple[str, str]: (auth_url, state)
    """
    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        raise HTTPException(status_code=503, detail="Google OAuth libraries unavailable")
    flow = create_flow()
    if state_payload:
        state = _sign_state(state_payload)
    else:
        state = _sign_state({"user_id": user_id})
    flow.state = state
    return flow.authorization_url()[0], state

def exchange_code(code: str, state: str, verify_state: bool = True) -> Any:
    """Exchange an authorization code for credentials.

    Args:
        code: Authorization code from Google
        state: State parameter (verified if verify_state=True)
        verify_state: Whether to verify the state parameter

    Returns:
        Credentials object with token, refresh_token, etc.

    Raises:
        HTTPException: On exchange failure or invalid state
    """
    if verify_state:
        try:
            _verify_state(state)
        except Exception as e:
            logger.error(
                "State verification failed",
                extra={
                    "meta": {
                        "error_class": "StateVerificationError",
                        "error_detail": str(e),
                        "cause": "Invalid or expired state parameter"
                    }
                }
            )
            raise HTTPException(status_code=400, detail="Invalid state")

    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        # Optional google libs are unavailable; fall back to manual token exchange below.
        # We still attempt the manual HTTP token exchange to support lightweight environments.
        logger.warning("Google OAuth client libs unavailable; using manual token exchange")
    
    # First try via official client (if available)
    try:
        from ...otel_utils import start_span

        # Record whether PKCE was used (best-effort: present in code or flow)
        pkce_used = False
        try:
            pkce_used = bool(getattr(flow, "code_verifier", None) or "pkce" in getattr(flow, "scopes", []))
        except Exception:
            pkce_used = False

        with start_span("google.oauth.token.exchange", {"method": "google_client_lib", "pkce_used": pkce_used}) as _span:
            flow = create_flow()
            flow.fetch_token(code=code)
            logger.info(
                "Token exchange successful via Google client library",
                extra={
                    "meta": {
                        "method": "google_client_lib",
                        "status": "success",
                        "pkce_used": pkce_used,
                    }
                }
            )
            return flow.credentials
    except Exception as e:
        logger.warning(
            "Google client library token exchange failed, falling back to manual HTTP",
            extra={
                "meta": {
                    "method": "google_client_lib",
                    "status": "failed",
                    "error": str(e)
                }
            }
        )
        # Fallback: manual token exchange to avoid oauthlib scope_changed issues
        try:
            # Prefer requests if available for simplicity
            try:
                from datetime import datetime, timedelta

                import requests

                logger.info(
                    "Starting manual HTTP token exchange",
                    extra={
                        "meta": {
                            "method": "manual_http_requests",
                            "token_uri": CLIENT_CONFIG["web"]["token_uri"]
                        }
                    }
                )
                
                start_time = time.time()
                from ...otel_utils import start_span
                with start_span("google.oauth.token.exchange", {"method": "manual_http_requests"}) as _span:
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
                duration = (time.time() - start_time) * 1000
                
                if not resp.ok:
                    logger.error(
                        "Google token exchange failed",
                        extra={
                            "meta": {
                                "method": "manual_http_requests",
                                "status": resp.status_code,
                                "latency_ms": duration,
                                "error_class": "HTTPError",
                                "error_detail": f"HTTP {resp.status_code}",
                                "response_body": resp.text[:200] if resp.text else None
                            }
                        }
                    )
                    raise HTTPException(status_code=400, detail="oauth_exchange_failed")
                
                data = resp.json()
                logger.info(
                    "Manual HTTP token exchange successful",
                    extra={
                        "meta": {
                            "method": "manual_http_requests",
                            "status": resp.status_code,
                            "latency_ms": duration,
                            "has_access_token": "access_token" in data,
                            "has_refresh_token": "refresh_token" in data,
                            "has_id_token": "id_token" in data
                        }
                    }
                )
                
            except ModuleNotFoundError:
                # Fall back to stdlib when requests isn't installed
                import json as _json
                import urllib.parse
                import urllib.request
                from datetime import datetime, timedelta

                logger.info(
                    "Starting manual HTTP token exchange (stdlib)",
                    extra={
                        "meta": {
                            "method": "manual_http_stdlib",
                            "token_uri": CLIENT_CONFIG["web"]["token_uri"]
                        }
                    }
                )
                
                start_time = time.time()
                post_data = urllib.parse.urlencode({
                    "code": code,
                    "client_id": CLIENT_CONFIG["web"]["client_id"],
                    "client_secret": CLIENT_CONFIG["web"]["client_secret"],
                    "redirect_uri": CLIENT_CONFIG["web"]["redirect_uris"][0],
                    "grant_type": "authorization_code",
                }).encode()
                req = urllib.request.Request(
                    CLIENT_CONFIG["web"]["token_uri"],
                    data=post_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read().decode()
                    data = _json.loads(body)
                
                duration = (time.time() - start_time) * 1000
                logger.info(
                    "Manual HTTP token exchange successful (stdlib)",
                    extra={
                        "meta": {
                            "method": "manual_http_stdlib",
                            "status": resp.status,
                            "latency_ms": duration,
                            "has_access_token": "access_token" in data,
                            "has_refresh_token": "refresh_token" in data,
                            "has_id_token": "id_token" in data
                        }
                    }
                )

            class _SimpleCreds:
                def __init__(self, d):
                    self.token = d.get("access_token")
                    self.refresh_token = d.get("refresh_token")
                    self.id_token = d.get("id_token")
                    scope_raw = d.get("scope") or " ".join(get_google_scopes())
                    self.scopes = scope_raw.split()
                    expires_in = int(d.get("expires_in") or 3600)
                    self.expiry = datetime.now(UTC) + timedelta(seconds=expires_in)
                    self.token_uri = CLIENT_CONFIG["web"]["token_uri"]
                    self.client_id = CLIENT_CONFIG["web"]["client_id"]
                    self.client_secret = CLIENT_CONFIG["web"]["client_secret"]

            return _SimpleCreds(data)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Manual token exchange failed",
                extra={
                    "meta": {
                        "error_class": type(e).__name__,
                        "error_detail": str(e),
                        "cause": "Unexpected error during manual token exchange"
                    }
                }
            )
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
            expiry_dt = datetime.now(UTC) + timedelta(hours=1)
        elif isinstance(expiry, datetime):
            expiry_dt = expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)
        else:
            # objects with .timestamp()
            try:
                expiry_dt = datetime.fromtimestamp(expiry.timestamp(), tz=UTC)  # type: ignore[arg-type]
            except Exception:
                expiry_dt = datetime.now(UTC) + timedelta(hours=1)
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
