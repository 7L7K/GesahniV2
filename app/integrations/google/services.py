from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def _refresh(creds: Credentials) -> Credentials:
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "Failed to refresh Google credentials",
                extra={"meta": {"error": str(e)}},
            )
            # Return original creds - caller will handle expired tokens
    return creds


def gmail_service(creds: Credentials):
    creds = _refresh(creds)
    # cache_discovery=False avoids file writes in server envs
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def calendar_service(creds: Credentials):
    creds = _refresh(creds)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)
