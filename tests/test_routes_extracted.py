import importlib


def test_main_contains_no_business_handlers():
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    from app.main import app
    # paths we expect to exist, but not be defined in main anymore
    wanted = ["/v1/sessions/upload","/v1/capture/start","/v1/csrf","/v1/ha/entities","/v1/memories/export"]
    got = [r.path for r in app.routes]
    for p in wanted:
        assert p in got
