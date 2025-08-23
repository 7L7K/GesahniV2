from __future__ import annotations

import os

import httpx


class TwilioConfig:
    def __init__(self) -> None:
        self.sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER")

    @property
    def enabled(self) -> bool:
        return bool(self.sid and self.token and self.from_number)


async def send_sms(to_number: str, body: str) -> bool:
    cfg = TwilioConfig()
    if not cfg.enabled:
        # treat as success in environments where Twilio is not configured
        return True
    url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg.sid}/Messages.json"
    auth = (cfg.sid, cfg.token)
    data = {"From": cfg.from_number, "To": to_number, "Body": body}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, data=data, auth=auth)
            resp.raise_for_status()
        return True
    except Exception:
        return False


