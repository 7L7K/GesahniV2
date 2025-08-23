from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..integrations.twilio_sms import send_sms
from ..metrics import CARE_SMS_DLQ, CARE_SMS_RETRIES
from ..queue import get_queue

router = APIRouter(tags=["Care"])


async def sms_worker(name: str = "care_sms", *, _stop: asyncio.Event | None = None) -> None:
    q = get_queue(name)
    while True:
        if _stop and _stop.is_set():
            return
        job = await q.pop(timeout=1.0)
        if not job:
            await asyncio.sleep(0.1)
            continue
        to = job.get("to")
        body = job.get("body")
        retries = int(job.get("retries") or 0)
        ok = await send_sms(to, body)
        if not ok:
            retries += 1
            if retries <= 5:
                CARE_SMS_RETRIES.inc()
                # exponential backoff seconds
                backoff = min(60, 2 ** retries)
                await asyncio.sleep(backoff)
                await q.push({**job, "retries": retries})
            else:
                CARE_SMS_DLQ.inc()


