import json
import os
import pytest


def _openapi():
    from app.main import app
    return app.openapi()


async def _get(client, path: str):
    """Helper to make GET requests (calendar endpoints are public, no auth needed)."""
    response = await client.get(path)
    return response


@pytest.fixture(autouse=True)
def _calendar_tmpfile(monkeypatch, tmp_path):
    """Set up temporary calendar file for tests."""
    p = tmp_path / "calendar.json"
    p.write_text(
        json.dumps(
            [
                {"date": "2099-01-01", "time": "09:00", "title": "Future A"},
                {"date": "2099-01-02", "time": "10:00", "title": "Future B"},
                {"date": "1999-01-01", "time": "08:00", "title": "Past"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CALENDAR_FILE", str(p))
    yield


@pytest.mark.asyncio
async def test_calendar_next_returns_three_sorted(async_client):
    res = await _get(async_client, "/v1/calendar/next")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    # Only future two in our sample (past filtered), clamp to <=3
    titles = [it.get("title") for it in data["items"]]
    assert titles[:2] == ["Future A", "Future B"]


@pytest.mark.asyncio
async def test_calendar_list_returns_all_sorted(async_client):
    res = await _get(async_client, "/v1/calendar/list")
    assert res.status_code == 200
    items = res.json()["items"]
    # Sorted by date/time; past first
    assert [it["title"] for it in items] == ["Past", "Future A", "Future B"]


@pytest.mark.asyncio
async def test_calendar_today_filters_today_only(async_client, monkeypatch):
    # Freeze today to the past entry
    monkeypatch.setenv("PYTEST_FAKE_TODAY", "1999-01-01")
    # Monkeypatch date.today via environment indirection: override _dt.date.today
    import app.api.calendar as cal

    class _FakeDate(cal._dt.date):
        @classmethod
        def today(cls):
            from datetime import date as _d

            s = os.getenv("PYTEST_FAKE_TODAY") or super().today().isoformat()
            y, m, d = map(int, s.split("-"))
            return _d(year=y, month=m, day=d)

    cal._dt.date = _FakeDate  # type: ignore
    res = await _get(async_client, "/v1/calendar/today")
    assert res.status_code == 200
    items = res.json()["items"]
    assert [it["title"] for it in items] == ["Past"]


def test_openapi_calendar_models_present_with_examples():
    o = _openapi()
    tags = [t.get("name") for t in o.get("tags", [])]
    assert "Calendar" in tags
    schemas = o.get("components", {}).get("schemas", {})
    assert "Event" in schemas and "EventsResponse" in schemas
    assert "example" in schemas["Event"]
    assert "example" in schemas["EventsResponse"]


@pytest.mark.parametrize(
    "path",
    [
        "/v1/calendar/next",
        "/v1/calendar/today",
        "/v1/calendar/list",
    ],
)
def test_calendar_endpoints_tagged_calendar(path, client):
    o = _openapi()
    op = o.get("paths", {}).get(path, {}).get("get")
    assert op and "Calendar" in (op.get("tags") or [])


@pytest.mark.asyncio
async def test_calendar_response_shapes(async_client):
    for path in ("/v1/calendar/list", "/v1/calendar/next", "/v1/calendar/today"):
        res = await _get(async_client, f"{path}")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body.get("items"), list)
        for it in body["items"]:
            assert "date" in it


def test_calendar_openapi_status_code_200_has_model():
    o = _openapi()
    for path in ("/v1/calendar/list", "/v1/calendar/next", "/v1/calendar/today"):
        op = o.get("paths", {}).get(path, {}).get("get") or {}
        resp = (op.get("responses") or {}).get("200") or {}
        content = (resp.get("content") or {}).get("application/json") or {}
        schema = content.get("schema") or {}
        assert schema.get("$ref", "").endswith("/EventsResponse")
