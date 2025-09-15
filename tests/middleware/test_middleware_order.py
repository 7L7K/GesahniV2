# tests/test_middleware_order.py
import importlib


def test_middleware_order_dev(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_MODE", "1")
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    from app.main import app

    names = [m.cls.__name__ for m in getattr(app, "user_middleware", [])]

    # Canonical order: outermost middleware is CorsPreflightMiddleware
    assert names[-1] == "CorsPreflightMiddleware"
    assert "CSRFMiddleware" not in names  # CSRF disabled by default
    # Critical order: MetricsMiddleware BEFORE DeprecationHeaderMiddleware in execution
    # FastAPI executes middleware in user_middleware order (first to last)
    metrics_idx = names.index("MetricsMiddleware")
    deprecation_idx = names.index("DeprecationHeaderMiddleware")
    assert (
        metrics_idx < deprecation_idx
    ), f"MetricsMiddleware ({metrics_idx}) should execute before DeprecationHeaderMiddleware ({deprecation_idx})"
    # Inner cluster present
    for n in ["CORSMiddleware", "TraceRequestMiddleware", "RedactHashMiddleware"]:
        assert n in names
