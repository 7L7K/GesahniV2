from fastapi.testclient import TestClient

from app.main import app


def test_calendar_examples_present_in_openapi():
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/v1/calendar/today" in paths
    assert "/v1/calendar/next" in paths
    assert "/v1/calendar/list" in paths

    def _example_for(path: str):
        item = paths[path]
        # GET object
        methods = [k for k in item.keys() if k.lower() == "get"]
        assert methods
        get = item[methods[0]]
        content = get.get("responses", {}).get("200", {}).get("content", {})
        return content.get("application/json", {}).get("example")

    ex_today = _example_for("/v1/calendar/today")
    ex_next = _example_for("/v1/calendar/next")
    ex_list = _example_for("/v1/calendar/list")

    # Acceptance criteria: two sample events + one next
    assert isinstance(ex_today, dict)
    assert len(ex_today.get("items", [])) >= 2
    assert isinstance(ex_next, dict)
    assert len(ex_next.get("items", [])) >= 1
    assert isinstance(ex_list, dict)
    assert len(ex_list.get("items", [])) >= 2


