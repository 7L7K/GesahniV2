from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


@pytest.mark.parametrize(
    "origin,should_connect",
    [
        ("http://localhost:3000", True),
        ("https://evil.example", False),
    ],
)
def test_ws_origin_policy(origin, should_connect):
    c = TestClient(app)
    # Ensure JWT_SECRET unset so verify_ws doesn't require a token in this test
    with patch.dict("os.environ", {"JWT_SECRET": ""}):
        if should_connect:
            with c.websocket_connect("/v1/ws/health", headers={"Origin": origin}) as ws:
                assert ws.receive_text() == "healthy"
        else:
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect("/v1/ws/health", headers={"Origin": origin}):
                    pass
