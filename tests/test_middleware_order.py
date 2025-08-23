# tests/test_middleware_order.py
import importlib


def test_middleware_order_dev(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_MODE", "1")
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    from app.main import app
    names = [m.cls.__name__ for m in getattr(app, "user_middleware", [])]
    # Adjust for optional SilentRefresh/ReloadEnv toggles if you gate them
    # Current outermost middleware is RequestIDMiddleware
    assert names[-1] == "RequestIDMiddleware"
    assert "CSRFMiddleware" in names
    # Inner cluster present
    for n in ["CORSMiddleware","TraceRequestMiddleware","RedactHashMiddleware"]:
        assert n in names
