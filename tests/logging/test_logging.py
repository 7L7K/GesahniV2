import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import importlib
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ["OLLAMA_URL"] = "http://x"
os.environ["OLLAMA_MODEL"] = "llama3"
os.environ["HOME_ASSISTANT_URL"] = "http://ha"
os.environ["HOME_ASSISTANT_TOKEN"] = "token"
import app.http_utils as http_utils
from app import main
from app.logging_config import configure_logging  # noqa: F401


def test_request_id_header(monkeypatch):
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    client = TestClient(main.app)
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_http_logging_initialized_once(monkeypatch):
    http_logger = logging.getLogger("httpx")
    core_logger = logging.getLogger("httpcore")

    http_logger.setLevel(logging.NOTSET)
    core_logger.setLevel(logging.NOTSET)

    with (
        patch.object(http_logger, "setLevel") as http_set,
        patch.object(core_logger, "setLevel") as core_set,
    ):
        importlib.reload(http_utils)
        assert http_set.call_count == 1
        assert core_set.call_count == 1

        class DummyResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {}

        class DummyClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                pass

            async def request(self, method, url, **kwargs):
                return DummyResp()

        with patch("app.http_utils.httpx.AsyncClient", return_value=DummyClient()):
            await http_utils.json_request("GET", "http://example.com")

        assert http_set.call_count == 1
        assert core_set.call_count == 1
