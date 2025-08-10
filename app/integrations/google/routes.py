from __future__ import annotations
import base64, email.utils
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from .db import SessionLocal, GoogleToken, init_db
from .oauth import build_auth_url, exchange_code, creds_to_record, record_to_creds
from .services import gmail_service, calendar_service
from .config import validate_config
from ...deps.user import get_current_user_id

router = APIRouter()

@router.on_event("startup")
def _startup():
    validate_config()
    init_db()

@router.get("/auth/url")
def get_auth_url(user_id: str = Depends(get_current_user_id)):
    url, _state = build_auth_url(user_id)
    return {"auth_url": url}

@router.get("/oauth/callback")
def oauth_callback(code: str, state: str, user_id: str = Depends(get_current_user_id)):
    creds = exchange_code(code, state)
    data = creds_to_record(creds)
    with SessionLocal() as s:
        row = s.get(GoogleToken, user_id)
        if row is None:
            row = GoogleToken(user_id=user_id, **data)
            s.add(row)
        else:
            for k, v in data.items():
                setattr(row, k, v)
        s.commit()
    return {"status": "ok"}

class SendEmailIn(BaseModel):
    to: EmailStr
    subject: str
    body_text: str
    from_alias: Optional[str] = None  # e.g., "King <me@gmail.com>"

@router.post("/gmail/send")
def gmail_send(payload: SendEmailIn, user_id: str = Depends(get_current_user_id)):
    with SessionLocal() as s:
        row = s.get(GoogleToken, user_id)
        if not row:
            raise HTTPException(400, "No Google account linked")
        creds = record_to_creds(row)
        svc = gmail_service(creds)

        sender = payload.from_alias or "me"
        msg = (
            f"From: {sender}\r\n"
            f"To: {payload.to}\r\n"
            f"Subject: {payload.subject}\r\n"
            f"Date: {email.utils.formatdate(localtime=True)}\r\n"
            f"MIME-Version: 1.0\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{payload.body_text}\r\n"
        )
        raw = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("ascii")
        res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"id": res.get("id")}

class CreateEventIn(BaseModel):
    title: str
    start_iso: str  # "2025-08-11T10:00:00-04:00"
    end_iso: str    # "2025-08-11T10:30:00-04:00"
    description: Optional[str] = None
    attendees: Optional[List[EmailStr]] = None
    calendar_id: Optional[str] = "primary"
    location: Optional[str] = None

@router.post("/calendar/create")
def calendar_create(evt: CreateEventIn, user_id: str = Depends(get_current_user_id)):
    with SessionLocal() as s:
        row = s.get(GoogleToken, user_id)
        if not row:
            raise HTTPException(400, "No Google account linked")
        creds = record_to_creds(row)
        cal = calendar_service(creds)

        body = {
            "summary": evt.title,
            "description": evt.description,
            "start": {"dateTime": evt.start_iso},
            "end": {"dateTime": evt.end_iso},
        }
        if evt.attendees:
            body["attendees"] = [{"email": a} for a in evt.attendees]
        if evt.location:
            body["location"] = evt.location

        created = cal.events().insert(calendarId=evt.calendar_id, body=body, sendUpdates="all").execute()
        return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}

@router.get("/status")
def google_status(user_id: str = Depends(get_current_user_id)):
    with SessionLocal() as s:
        row = s.get(GoogleToken, user_id)
        if not row:
            return {"linked": False}
        return {
            "linked": True,
            "scopes": row.scopes.split(),
            "expiry": row.expiry.isoformat(),
        }
