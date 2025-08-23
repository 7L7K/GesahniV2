import datetime as dt

from fastapi.testclient import TestClient

from app.integrations.calendar_fake import DETROIT_TZ, FakeCalendarProvider
from app.main import app


def _tz():
    import zoneinfo

    return zoneinfo.ZoneInfo(DETROIT_TZ)


def test_provider_basic_local_and_utc_mapping():
    tz = _tz()
    prov = FakeCalendarProvider()
    s = dt.datetime(2025, 3, 15, 9, 0, 0, tzinfo=tz)
    e = dt.datetime(2025, 3, 15, 10, 0, 0, tzinfo=tz)
    prov.add_event("Breakfast", s, e)
    items = prov.list_next(5, now=dt.datetime(2025, 3, 15, 8, 0, tzinfo=tz))
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "Breakfast"
    assert it["start_local"].endswith("-04:00") or it["start_local"].endswith("-05:00")
    assert it["start_utc"].endswith("Z")


def test_dst_spring_forward_gap():
    tz = _tz()
    # US Eastern DST 2025-03-09 02:00 -> 03:00; 02:30 does not exist
    prov = FakeCalendarProvider()
    s = dt.datetime(2025, 3, 9, 3, 0, tzinfo=tz)
    e = dt.datetime(2025, 3, 9, 4, 0, tzinfo=tz)
    prov.add_event("Post-DST", s, e)
    out = prov.list_next(3, now=dt.datetime(2025, 3, 9, 1, 0, tzinfo=tz))
    assert out[0]["title"] == "Post-DST"


def test_dst_fall_back_ambiguous_hour():
    tz = _tz()
    prov = FakeCalendarProvider()
    # Fall back 2025-11-02; 1:30 occurs twice; rely on tzinfo handling
    s = dt.datetime(2025, 11, 2, 1, 30, tzinfo=tz)
    e = dt.datetime(2025, 11, 2, 2, 30, tzinfo=tz)
    prov.add_event("Ambiguous", s, e)
    out = prov.list_next(3, now=dt.datetime(2025, 11, 2, 0, 0, tzinfo=tz))
    assert out[0]["title"] == "Ambiguous"


def test_api_calendar_next_uses_fake_provider(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    r = c.get("/v1/calendar/next")
    # Response model is EventsResponse with simplified items mapping
    assert r.status_code == 200
    assert "items" in r.json()


def test_build_event_outputs_expected_keys():
    tz = _tz()
    prov = FakeCalendarProvider()
    s = dt.datetime(2025, 5, 1, 12, 0, tzinfo=tz)
    e = dt.datetime(2025, 5, 1, 12, 30, tzinfo=tz)
    ev = prov.build_event("Lunch", s, e)
    assert set(["title", "start_local", "end_local", "start_utc", "end_utc", "tz"]).issubset(ev.keys())


def test_ics_parser_local_and_utc(tmp_path):
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "SUMMARY:Zed",
                "DTSTART;TZID=America/Detroit:20250315T090000",
                "DTEND;TZID=America/Detroit:20250315T093000",
                "END:VEVENT",
                "BEGIN:VEVENT",
                "SUMMARY:UTC",
                "DTSTART:20250315T140000Z",
                "DTEND:20250315T143000Z",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
    )
    prov = FakeCalendarProvider(ics_path=str(ics))
    out = prov.list_next(5, now=dt.datetime(2025, 3, 15, 8, 0))
    titles = [e["title"] for e in out]
    assert "Zed" in titles and "UTC" in titles


def test_list_next_sorts_by_utc():
    tz = _tz()
    prov = FakeCalendarProvider()
    prov.add_event("B", dt.datetime(2025, 5, 1, 10, 0, tzinfo=tz), dt.datetime(2025, 5, 1, 11, 0, tzinfo=tz))
    prov.add_event("A", dt.datetime(2025, 5, 1, 9, 0, tzinfo=tz), dt.datetime(2025, 5, 1, 10, 0, tzinfo=tz))
    out = prov.list_next(5, now=dt.datetime(2025, 5, 1, 8, 0, tzinfo=tz))
    assert [e["title"] for e in out] == ["A", "B"]


