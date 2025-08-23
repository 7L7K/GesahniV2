from __future__ import annotations

import asyncio
import os
import time

from .care_store import list_devices, set_device_flags
from .integrations.twilio_sms import send_sms
from .metrics import ALERT_SEND_FAILURES


async def heartbeat_monitor_loop(poll_seconds: int = 30) -> None:
    """Background loop to mark offline devices and send battery low notifications."""
    if os.getenv("HEARTBEAT_ENFORCE", "1").lower() not in {"1", "true", "yes", "on"}:
        return
    while True:
        try:
            now = time.time()
            devices = await list_devices()
            for d in devices:
                last = float(d.get("last_seen") or 0.0)
                offline = now - last > 90.0
                if offline and not d.get("offline_since"):
                    await set_device_flags(
                        d["id"], offline_since=now, offline_notified=0
                    )
                elif not offline and d.get("offline_since"):
                    await set_device_flags(
                        d["id"], offline_since=None, offline_notified=0
                    )

                batt = d.get("battery_pct")
                if batt is not None and batt < 15:
                    low_since = d.get("battery_low_since") or now
                    notified = int(d.get("battery_notified") or 0)
                    # If low for > 5 minutes and not notified, send SMS (stub)
                    if now - float(low_since) > 300 and not notified:
                        ok = await send_sms(
                            os.getenv("TWILIO_TEST_TO", "+10000000000"),
                            f"Battery low on device {d['id']} ({batt}%).",
                        )
                        if ok:
                            await set_device_flags(d["id"], battery_notified=1)
                        else:
                            ALERT_SEND_FAILURES.labels("sms").inc()
                else:
                    # reset low battery flags when recovered
                    if d.get("battery_low_since") or d.get("battery_notified"):
                        await set_device_flags(
                            d["id"], battery_low_since=None, battery_notified=0
                        )
        except Exception:
            pass
        await asyncio.sleep(poll_seconds)
