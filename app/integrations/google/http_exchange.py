import time
import logging
import os
from typing import Any

import httpx

from .constants import ERR_OAUTH_EXCHANGE_FAILED, ERR_OAUTH_INVALID_GRANT
from .errors import OAuthError

logger = logging.getLogger(__name__)


async def async_token_exchange(
    code: str,
    code_verifier: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    redirect_uri: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Perform async token exchange against Google's token endpoint.

    Raises OAuthError on sanitized failures.
    """
    token_url = "https://oauth2.googleapis.com/token"
    # Allow caller to pass client credentials; fall back to env-configured values
    client_id = client_id or os.getenv("GOOGLE_CLIENT_ID")
    client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = redirect_uri or os.getenv("GOOGLE_REDIRECT_URI")

    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(token_url, data=data, headers=headers)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            logger.warning("google_token_exchange_failed: network", extra={"meta": {"error": str(exc)}})
            # Map network/timeout to sanitized OAuthError
            raise OAuthError(code=ERR_OAUTH_EXCHANGE_FAILED, http_status=504, reason="timeout", extra=None)

        # Always avoid logging tokens
        if r.status_code != 200:
            # Try to parse error body but keep parsing errors separate from
            # OAuthError we intentionally raise for invalid_grant.
            err = {}
            try:
                err = r.json()
            except Exception:
                err = {}

            # Log the Google error response for debugging
            logger.warning(
                "Google OAuth token exchange failed",
                extra={
                    "meta": {
                        "google_status_code": r.status_code,
                        "google_response": err,
                        "google_error": err.get("error"),
                        "google_error_description": err.get("error_description"),
                        "has_error_body": bool(err),
                    }
                },
            )

            if isinstance(err, dict) and err.get("error") == "invalid_grant":
                raise OAuthError(code=ERR_OAUTH_INVALID_GRANT, http_status=400, reason="invalid_grant", extra=None)

            # Generic exchange failure
            raise OAuthError(code=ERR_OAUTH_EXCHANGE_FAILED, http_status=400, reason="exchange_failed", extra=None)

        td = r.json()
        now = int(time.time())
        expires_in = int(td.get("expires_in", 3600))
        td["expires_at"] = now + expires_in

        # Log the full Google response for debugging (with secrets redacted)
        loggable_response = td.copy()
        if "access_token" in loggable_response:
            loggable_response["access_token"] = f"[REDACTED:{len(loggable_response['access_token'])}chars]"
        if "refresh_token" in loggable_response and loggable_response["refresh_token"]:
            loggable_response["refresh_token"] = f"[REDACTED:{len(loggable_response['refresh_token'])}chars]"
        if "id_token" in loggable_response and loggable_response["id_token"]:
            loggable_response["id_token"] = f"[REDACTED:{len(loggable_response['id_token'])}chars]"

        logger.info(
            "Google OAuth token exchange successful",
            extra={
                "meta": {
                    "google_response": loggable_response,
                    "has_access_token": "access_token" in td,
                    "has_refresh_token": bool(td.get("refresh_token")),
                    "has_id_token": bool(td.get("id_token")),
                    "id_token_length": len(td.get("id_token", "")),
                    "token_type": td.get("token_type"),
                    "scope": td.get("scope"),
                    "expires_in": td.get("expires_in"),
                }
            },
        )

        return td


