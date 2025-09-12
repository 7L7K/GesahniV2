from __future__ import annotations

import os
import time
import secrets
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ...models.third_party_tokens import ThirdPartyToken

logger = logging.getLogger(__name__)


@dataclass
class GoogleTokenResponse:
    access_token: str
    refresh_token: str | None
    scope: str | None
    expires_at: int


from .errors import OAuthError
from .constants import ERR_OAUTH_EXCHANGE_FAILED, ERR_OAUTH_INVALID_GRANT, METRIC_TOKEN_EXCHANGE_FAILED, METRIC_TOKEN_EXCHANGE_OK
from .http_exchange import async_token_exchange


class GoogleOAuthError(Exception):
    pass


class InvalidGrantError(GoogleOAuthError):
    """Special exception for invalid_grant errors (user revoked consent)."""
    pass


class GoogleOAuth:
    def __init__(self) -> None:
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
        self.scopes = os.getenv("GOOGLE_SCOPES", "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly").strip()

        # Do not raise during construction; allow callers/tests to construct
        # the helper even when env vars are not populated. Validation that
        # credentials exist should be performed at the integration callsite
        # (e.g. when building real flows or hitting Google's endpoints).
        if not self.client_id or not self.client_secret:
            logger.debug("Google OAuth credentials not configured (GOOGLE_CLIENT_ID/SECRET missing)")

    def get_authorization_url(self, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str, code_verifier: str | None = None) -> dict[str, Any]:
        # Enforce PKCE presence and length
        if not code_verifier or not (43 <= len(code_verifier) <= 128):
            from .errors import OAuthError as _OAuthError
            from .constants import ERR_OAUTH_EXCHANGE_FAILED

            raise _OAuthError(code=ERR_OAUTH_EXCHANGE_FAILED, http_status=400, reason="missing_or_invalid_pkce", extra=None)

        # Call unified async token exchange helper and emit metrics
        from ...metrics import GOOGLE_TOKEN_EXCHANGE_OK, GOOGLE_TOKEN_EXCHANGE_FAILED
        try:
            td = await async_token_exchange(code, code_verifier=code_verifier)
            try:
                scopes_hash = "unknown"
                GOOGLE_TOKEN_EXCHANGE_OK.labels(user_id="unknown", scopes_hash=scopes_hash).inc()
            except Exception:
                pass
            return td
        except OAuthError:
            # Integration layer will have sanitized the OAuthError; emit failure metric and re-raise
            try:
                GOOGLE_TOKEN_EXCHANGE_FAILED.labels(user_id="unknown", reason="oauth_error").inc()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error("Token exchange unexpected error", extra={"meta": {"error": str(e)}})
            try:
                GOOGLE_TOKEN_EXCHANGE_FAILED.labels(user_id="unknown", reason="internal_error").inc()
            except Exception:
                pass
            from .errors import OAuthError as _OAuthError
            from .constants import ERR_OAUTH_EXCHANGE_FAILED

            raise _OAuthError(code=ERR_OAUTH_EXCHANGE_FAILED, http_status=500, reason="internal_error", extra=None)

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Retry once on network errors/timeouts
            try:
                r = await client.post(token_url, data=data, headers=headers)
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                try:
                    r = await client.post(token_url, data=data, headers=headers)
                except Exception:
                    raise GoogleOAuthError(f"Token refresh failed: network error: {exc}")

            if r.status_code != 200:
                # Check for invalid_grant error (user revoked consent)
                try:
                    error_data = r.json()
                    if error_data.get("error") == "invalid_grant":
                        # Create a special error for invalid_grant to distinguish from other failures
                        raise InvalidGrantError(f"Token refresh failed due to invalid_grant: {r.status_code} {r.text}")
                except Exception:
                    pass  # Fall through to generic error
                raise GoogleOAuthError(f"Token refresh failed: {r.status_code} {r.text}")
            td = r.json()
            now = int(time.time())
            expires_in = int(td.get("expires_in", 3600))
            td["expires_at"] = now + expires_in
            # Google may not return a refresh_token on refresh
            if "refresh_token" not in td:
                td["refresh_token"] = refresh_token
            return td


async def gmail_unread_count(access_token: str) -> int:
    """Small probe: return unread Gmail message count for primary mailbox."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://www.googleapis.com/gmail/v1/users/me/messages"
    params = {"q": "is:unread", "maxResults": 0}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers=headers, params=params)
        if r.status_code != 200:
            raise GoogleOAuthError(f"Gmail probe failed: {r.status_code} {r.text}")
        data = r.json()
        return int(data.get("resultSizeEstimate", 0))


async def calendar_next_event(access_token: str) -> dict | None:
    """Small probe: return the next upcoming event for the primary calendar."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    params = {"orderBy": "startTime", "singleEvents": True, "maxResults": 1, "timeMin": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers=headers, params=params)
        if r.status_code != 200:
            raise GoogleOAuthError(f"Calendar probe failed: {r.status_code} {r.text}")
        data = r.json()
        items = data.get("items", [])
        return items[0] if items else None


def make_authorize_url(state: str) -> str:
    return GoogleOAuth().get_authorization_url(state)


async def exchange_code(code: str, state: str | None = None, verify_state: bool = True, code_verifier: str | None = None):
    """Exchange an authorization code for Google credentials.

    If `state` is provided and `verify_state` is True, the state will be verified
    (consuming nonce when applicable). Returns Google credentials object that
    the callback can use for further processing.
    """
    if state and verify_state:
        try:
            _verify_state(state)
        except Exception:
            from ..error_envelope import raise_enveloped

            raise_enveloped("invalid_state", "Invalid state", hint="Retry the OAuth flow", status=400)

    oauth = GoogleOAuth()
    td = await oauth.exchange_code_for_tokens(code, code_verifier)

    # Create Google credentials object
    if not _GOOGLE_AVAILABLE or _Credentials is None:  # pragma: no cover - env-dependent
        from ..error_envelope import raise_enveloped
        raise_enveloped("google_unavailable", "google credentials unavailable", status=501)

    now = int(time.time())
    expires_at = int(td.get("expires_at", now + int(td.get("expires_in", 3600))))

    # Convert expires_at timestamp to datetime
    from datetime import datetime, UTC
    expiry_dt = datetime.fromtimestamp(expires_at, tz=UTC)

    creds = _Credentials(
        token=td.get("access_token", ""),
        refresh_token=td.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        scopes=td.get("scope", "").split() if td.get("scope") else [],
        expiry=expiry_dt,
    )

    # Add id_token so the callback can access it. Some Credentials implementations
    # expose `id_token` as a read-only property which raises on assignment. To be
    # robust for both real google Credentials and test/mocked objects, try to
    # attach the attribute directly; if that fails, return a small proxy that
    # exposes `id_token` while delegating other attribute access to the real
    # credentials object.
    id_token_val = td.get("id_token")
    if id_token_val:
        try:
            setattr(creds, "id_token", id_token_val)
        except Exception:
            # Create a lightweight proxy wrapper that exposes id_token and
            # forwards other attribute lookups to the underlying creds object.
            class _CredentialsProxy:
                def __init__(self, inner, id_token):
                    object.__setattr__(self, "_inner", inner)
                    object.__setattr__(self, "id_token", id_token)

                def __getattr__(self, name):
                    return getattr(self._inner, name)

                def __setattr__(self, name, value):
                    # Try to set on inner if it has attribute, otherwise set on proxy
                    try:
                        setattr(self._inner, name, value)
                    except Exception:
                        object.__setattr__(self, name, value)

                def __repr__(self):
                    return f"CredentialsProxy({repr(self._inner)})"

            return _CredentialsProxy(creds, id_token_val)

    return creds


async def refresh_token(refresh_token: str) -> dict[str, Any]:
    oauth = GoogleOAuth()
    return await oauth.refresh_access_token(refresh_token)

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
        from ...error_envelope import raise_enveloped

        raise_enveloped("invalid_state", "Invalid state", hint="retry the OAuth flow", status=400)


def create_flow(scopes: list[str] | None = None):
    """Return a google-auth ``Flow`` when libraries are available.

    Raises HTTPException when unavailable so callers can degrade gracefully.
    """
    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        from ...error_envelope import raise_enveloped

        raise_enveloped("unavailable", "Google OAuth libraries unavailable", status=503)
    return _Flow.from_client_config(CLIENT_CONFIG, scopes=scopes or get_google_scopes())


def build_auth_url(user_id: str, state_payload: dict | None = None) -> tuple[str, str]:
    """Build a Google OAuth URL with optional state payload.

    Returns:
        Tuple[str, str]: (auth_url, state)
    """
    if not _GOOGLE_AVAILABLE or _Flow is None:  # pragma: no cover - env-dependent
        from ...error_envelope import raise_enveloped

        raise_enveloped("unavailable", "Google OAuth libraries unavailable", status=503)

    # Debug: Log what scopes will be used
    current_scopes = get_google_scopes()
    logger.info("🎵 GOOGLE BUILD_AUTH_URL: Scopes being used", extra={
        "meta": {
            "user_id": user_id,
            "scopes": current_scopes,
            "scopes_count": len(current_scopes)
        }
    })

    flow = create_flow()
    # Ensure redirect_uri is explicitly set on the Flow before generating the
    # authorization URL so Google receives it as a parameter. Some environments
    # do not propagate redirect_uris from client config until explicitly set.
    try:  # best-effort; fall back silently if unavailable
        flow.redirect_uri = CLIENT_CONFIG["web"]["redirect_uris"][0]
    except Exception:
        pass
    if state_payload:
        state = _sign_state(state_payload)
    else:
        state = _sign_state({"user_id": user_id})
    flow.state = state
    return flow.authorization_url()[0], state



def refresh_if_needed(creds: Any) -> Any:
    try:
        expired = getattr(creds, "expired", False)
        has_refresh = getattr(creds, "refresh_token", None)
        if (
            expired and has_refresh and _GOOGLE_AVAILABLE and _Request is not None
        ):  # pragma: no cover
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
            "access_token": getattr(creds, "access_token", None),
            "refresh_token": getattr(creds, "refresh_token", None),
            "token_uri": getattr(
                creds, "token_uri", "https://oauth2.googleapis.com/token"
            ),
            "client_id": getattr(creds, "client_id", GOOGLE_CLIENT_ID),
            "client_secret": getattr(creds, "client_secret", GOOGLE_CLIENT_SECRET),
            "scopes": " ".join(scopes),
            "expiry": expiry_dt,
        }
    except Exception as e:  # pragma: no cover - defensive
        from ..error_envelope import raise_enveloped

        raise_enveloped("bad_credentials_object", f"bad credentials object: {e}", status=400)


def record_to_creds(record):
    if (
        not _GOOGLE_AVAILABLE or _Credentials is None
    ):  # pragma: no cover - env-dependent
        from ..error_envelope import raise_enveloped

        raise_enveloped("google_unavailable", "google credentials unavailable", status=501)
    return _Credentials(
        token=record.access_token,
        refresh_token=record.refresh_token,
        token_uri=record.token_uri,
        client_id=record.client_id,
        client_secret=record.client_secret,
        scopes=record.scopes.split(),
        expiry=record.expiry,
    )
