from __future__ import annotations
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def _refresh(creds: Credentials) -> Credentials:
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

def gmail_service(creds: Credentials):
    _refresh(creds)
    # cache_discovery=False avoids file writes in server envs
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def calendar_service(creds: Credentials):
    _refresh(creds)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)
