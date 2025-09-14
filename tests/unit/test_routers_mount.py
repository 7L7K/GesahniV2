import os

from fastapi import FastAPI

from app.routers.config import register_routers


def test_register_routers_mounts_without_error():
    app = FastAPI()
    # Ensure test env behaves like dev/test for fail-fast behavior
    os.environ.pop("ENV", None)
    os.environ["PYTEST_RUNNING"] = "1"

    # Should not raise when including routers into a fresh app in test mode
    register_routers(app)

    # Check that features_mounted exists on app.state (best-effort)
    mounted = getattr(app.state, "features_mounted", None)
    assert isinstance(mounted, dict) or mounted is None
