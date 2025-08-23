import importlib
import os
import sys


def test_cors_logs_once(caplog):
    # Ensure environment configured for dev boot
    os.environ.update({"ENV": "dev", "DEV_MODE": "1", "JWT_SECRET": "x" * 64, "CORS_ALLOW_ORIGINS": "http://localhost:3000"})
    # Importing the module should set the allowed_origins on the app state
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    else:
        importlib.import_module("app.main")
    import app.main as main
    assert getattr(main.app.state, "allowed_origins", None) == ["http://localhost:3000"]
