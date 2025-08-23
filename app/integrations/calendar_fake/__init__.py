from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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

    def __init__(self, tz_name: str = DETROIT_TZ, ics_path: str | None = None, events: list[SimpleEvent] | None = None) -> None:
        self.tz_name = tz_name
        self.tz = ZoneInfo(tz_name) if ZoneInfo is not None else None
        self.ics_path = Path(ics_path) if ics_path else None
        self._events: list[SimpleEvent] = events or []

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
    def list_next(self, n: int = 3, now: _dt.datetime | None = None) -> list[dict]:
        events: list[SimpleEvent] = []
        if self.ics_path and self.ics_path.exists():
            events.extend(self._read_ics(self.ics_path))
        events.extend(self._events)
        # Normalize 'now' to UTC for consistent filtering/sorting
        if now is None:
            base_now = _dt.datetime.now(tz=self.tz) if self.tz is not None else _dt.datetime.now()
        else:
            base_now = now
        if base_now.tzinfo is None and self.tz is not None:
            base_now = base_now.replace(tzinfo=self.tz)
        now_utc = base_now.astimezone(_dt.UTC) if base_now.tzinfo is not None else base_now
        try:
            logging.getLogger(__name__).debug(
                "calendar_now",
                extra={
                    "meta": {
                        "now_input": str(now),
                        "assumed_tz": self.tz_name,
                        "now_utc": now_utc.isoformat(),
                    }
                },
            )
        except Exception:
            pass
        out: list[dict] = []
        for ev in events:
            s_loc = self._as_local(ev.start)
            s_utc = self._to_utc(s_loc)
            if s_utc >= now_utc:  # include same-day boundary
                out.append(self.build_event(ev.title, ev.start, ev.end))
        # Sort by UTC ISO timestamps for determinism
        out.sort(key=lambda e: e["start_utc"])  # ISO-8601 Z timestamps sort lexicographically correctly
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
        return dt.astimezone(_dt.UTC)

    def _read_ics(self, path: Path) -> list[SimpleEvent]:
        """Very small ICS parser supporting DTSTART/DTEND/SUMMARY with TZID.

        Supports lines like:
          - DTSTART:YYYYMMDDTHHMMSSZ (UTC)
          - DTSTART;TZID=America/Detroit:YYYYMMDDTHHMMSS (local in TZID)
        """
        try:
            # Read and unfold RFC 5545 folded lines (continuations start with a single space)
            raw_lines = path.read_text(encoding="utf-8").splitlines()
            lines: list[str] = []
            for _ln in raw_lines:
                if _ln.startswith(" ") and lines:
                    lines[-1] += _ln[1:]
                else:
                    lines.append(_ln)
        except Exception:
            return []
        current: dict = {}
        out: list[SimpleEvent] = []
        for raw in lines:
            line = raw.strip()
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT":
                try:
                    title = str(current.get("SUMMARY") or "Event")
                    s = current.get("__START_DT__")
                    e = current.get("__END_DT__")
                    if not isinstance(s, _dt.datetime) or not isinstance(e, _dt.datetime):
                        continue
                    out.append(SimpleEvent(title=title, start=s, end=e))
                    # Best-effort debug log
                    try:
                        s_loc = self._as_local(s)
                        s_utc = self._to_utc(s_loc)
                        logging.getLogger(__name__).debug(
                            "calendar_ics_event",
                            extra={
                                "meta": {
                                    "title": title,
                                    "start_local": s_loc.isoformat(),
                                    "start_utc": s_utc.isoformat(),
                                }
                            },
                        )
                    except Exception:
                        pass
                except Exception:
                    pass
                current = {}
            else:
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                # Normalize keys and capture DTSTART/DTEND with optional TZID param
                base = key.split(";", 1)[0].upper()
                # params = key[len(base):]  # not used but kept for clarity
                tzid: str | None = None
                if ";" in key:
                    # Parse parameters like ";TZID=America/Detroit;VALUE=DATE-TIME"
                    try:
                        param_str = key.split(";", 1)[1]
                        for piece in param_str.split(";"):
                            if piece.upper().startswith("TZID="):
                                tzid = piece.split("=", 1)[1]
                                break
                    except Exception:
                        tzid = None
                if base == "DTSTART":
                    try:
                        current["__START_DT__"] = self._parse_ics_dt_value(val, tzid)
                    except Exception:
                        pass
                elif base == "DTEND":
                    try:
                        current["__END_DT__"] = self._parse_ics_dt_value(val, tzid)
                    except Exception:
                        pass
                elif base == "SUMMARY":
                    current["SUMMARY"] = val
                else:
                    # Keep raw in case of future expansion
                    current[key] = val
        return out

    def _parse_ics_dt(self, value: str) -> _dt.datetime:
        """Backward-compatible parser for legacy callers expecting only a value.

        Delegates to _parse_ics_dt_value without an explicit TZID (uses provider tz).
        """
        return self._parse_ics_dt_value(value, None)

    def _parse_ics_dt_value(self, value: str, tzid: str | None) -> _dt.datetime:
        """Parse an ICS date-time value with an optional TZID parameter.

        - If the value ends with 'Z', treat as UTC and convert to tzid or provider tz.
        - If tzid is provided, treat the naive value as local in that timezone.
        - Otherwise, treat naive value as local in provider timezone.
        """
        # UTC form
        if value.endswith("Z"):
            dt = _dt.datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=_dt.UTC)
            # Convert to specific tz if requested; otherwise leave in UTC
            if tzid and ZoneInfo is not None:
                try:
                    return dt.astimezone(ZoneInfo(tzid))
                except Exception:
                    pass
            return dt if self.tz is None else dt.astimezone(self.tz)
        # Local with tzid
        if tzid and ZoneInfo is not None:
            try:
                tz_local = ZoneInfo(tzid)
            except Exception:
                tz_local = self.tz
        else:
            tz_local = self.tz
        # Parse with seconds, then fallback without seconds
        try:
            naive = _dt.datetime.strptime(value, "%Y%m%dT%H%M%S")
        except Exception:
            naive = _dt.datetime.strptime(value, "%Y%m%dT%H%M")
        if tz_local is not None:
            return naive.replace(tzinfo=tz_local)
        return naive


__all__ = ["FakeCalendarProvider", "SimpleEvent", "DETROIT_TZ"]


