from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover - fallback for very old Pythons
    ZoneInfo = None  # type: ignore


DETROIT_TZ = "America/Detroit"


@dataclass
class SimpleEvent:
    title: str
    start: _dt.datetime  # timezone-aware or naive local
    end: _dt.datetime    # timezone-aware or naive local


class FakeCalendarProvider:
    """A lightweight calendar provider for development.

    - Defaults to America/Detroit timezone
    - Supports in-memory events or a minimal .ics file (DTSTART/DTEND/SUMMARY)
    - Returns both local and UTC ISO8601 strings
    """

    def __init__(self, tz_name: str = DETROIT_TZ, ics_path: Optional[str] = None, events: Optional[List[SimpleEvent]] = None) -> None:
        self.tz_name = tz_name
        self.tz = ZoneInfo(tz_name) if ZoneInfo is not None else None
        self.ics_path = Path(ics_path) if ics_path else None
        self._events: List[SimpleEvent] = events or []

    # ----------------------
    # Public construction API
    # ----------------------
    def add_event(self, title: str, start_local: _dt.datetime, end_local: _dt.datetime) -> None:
        self._events.append(SimpleEvent(title=title, start=start_local, end=end_local))

    def build_event(self, title: str, start_local: _dt.datetime, end_local: _dt.datetime) -> dict:
        """Build an output event dict from naive or aware local datetimes.

        Naive datetimes are assumed to be in the provider's local timezone.
        """
        s_loc = self._as_local(start_local)
        e_loc = self._as_local(end_local)
        s_utc = self._to_utc(s_loc)
        e_utc = self._to_utc(e_loc)
        return {
            "title": title,
            "start_local": s_loc.isoformat(),
            "end_local": e_loc.isoformat(),
            "start_utc": s_utc.isoformat().replace("+00:00", "Z"),
            "end_utc": e_utc.isoformat().replace("+00:00", "Z"),
            "tz": self.tz_name,
        }

    # ---------------
    # Listing API
    # ---------------
    def list_next(self, n: int = 3, now: Optional[_dt.datetime] = None) -> List[dict]:
        events: List[SimpleEvent] = []
        if self.ics_path and self.ics_path.exists():
            events.extend(self._read_ics(self.ics_path))
        events.extend(self._events)
        # Filter by >= now
        now = now or _dt.datetime.now(tz=self.tz) if self.tz else _dt.datetime.now()
        out: List[dict] = []
        for ev in events:
            s_loc = self._as_local(ev.start)
            if s_loc >= self._as_local(now):
                out.append(self.build_event(ev.title, ev.start, ev.end))
        out.sort(key=lambda e: e["start_utc"])  # sort by UTC for determinism
        return out[: max(0, int(n))]

    # -----------------
    # Internal helpers
    # -----------------
    def _as_local(self, dt: _dt.datetime) -> _dt.datetime:
        if self.tz is None:
            return dt
        if dt.tzinfo is None:
            # PEP 495: fold info may be embedded; preserve if present
            try:
                dt = dt.replace(tzinfo=self.tz)
            except Exception:
                dt = dt.replace(tzinfo=self.tz)
            return dt
        return dt.astimezone(self.tz)

    def _to_utc(self, dt: _dt.datetime) -> _dt.datetime:
        if self.tz is None:
            return dt
        return dt.astimezone(_dt.timezone.utc)

    def _read_ics(self, path: Path) -> List[SimpleEvent]:
        """Very small ICS parser supporting DTSTART/DTEND/SUMMARY.

        Handles:
          - DTSTART:YYYYMMDDTHHMMSSZ (UTC)
          - DTSTART;TZID=America/Detroit:YYYYMMDDTHHMMSS (local)
        """
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        current: dict = {}
        out: List[SimpleEvent] = []
        for raw in lines:
            line = raw.strip()
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT":
                try:
                    title = str(current.get("SUMMARY") or "Event")
                    dtstart = current.get("DTSTART")
                    dtend = current.get("DTEND")
                    if not dtstart or not dtend:
                        continue
                    s = self._parse_ics_dt(dtstart)
                    e = self._parse_ics_dt(dtend)
                    out.append(SimpleEvent(title=title, start=s, end=e))
                except Exception:
                    pass
                current = {}
            else:
                if ":" in line:
                    key, val = line.split(":", 1)
                    current[key] = val
        return out

    def _parse_ics_dt(self, value: str) -> _dt.datetime:
        # Handle TZID param
        tz = self.tz
        if value.endswith("Z"):
            # UTC
            dt = _dt.datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=_dt.timezone.utc)
            return dt if tz is None else dt.astimezone(tz)
        # TZID=America/Detroit:YYYYMMDDTHHMMSS
        if value.startswith("TZID=") and ":" in value:
            _, rest = value.split(":", 1)
            dt = _dt.datetime.strptime(rest, "%Y%m%dT%H%M%S")
            return self._as_local(dt)
        # Bare local
        try:
            dt = _dt.datetime.strptime(value, "%Y%m%dT%H%M%S")
        except Exception:
            # try without seconds
            dt = _dt.datetime.strptime(value, "%Y%m%dT%H%M")
        return self._as_local(dt)


__all__ = ["FakeCalendarProvider", "SimpleEvent", "DETROIT_TZ"]


