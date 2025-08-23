import importlib


def test_middleware_order_contract(monkeypatch):
    # Ensure dev mode so optional dev middleware are present
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("SILENT_REFRESH_ENABLED", "1")

    # Force re-import of app.main to get a fresh middleware stack
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    from app.main import app

    names = [m.cls.__name__ for m in app.user_middleware]

    # The actual middleware order (outer→inner as reported by Starlette)
    assert names == [
        "CORSMiddleware",
        "EnhancedErrorHandlingMiddleware",
        "SilentRefreshMiddleware",
        "ReloadEnvMiddleware",
        "CSRFMiddleware",
        "SessionAttachMiddleware",
        "RateLimitMiddleware",
        "MetricsMiddleware",
        "RedactHashMiddleware",
        "AuditMiddleware",
        "TraceRequestMiddleware",
        "HealthCheckFilterMiddleware",
        "DedupMiddleware",
        "RequestIDMiddleware",
    ]


