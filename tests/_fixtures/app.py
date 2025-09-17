import os

import pytest

# Ensure app startup uses the CI/test profile to avoid spawning background daemons
os.environ.setdefault("ENV", "test")
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("CI", "1")

from starlette.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="function")
def client(app):
    # Function-scope client to isolate cookies/session between tests
    with TestClient(app) as c:
        yield c
