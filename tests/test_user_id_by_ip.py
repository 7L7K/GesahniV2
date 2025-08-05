from fastapi import Depends
from fastapi.testclient import TestClient

from app.deps.user import get_current_user_id
from app.security import rate_limit
from app.main import app
import app.security as security


@app.get("/whoami")
async def whoami(
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit),
):
    return {"user_id": user_id}


def test_unauthenticated_requests_are_rate_limited_per_ip(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(security, "RATE_LIMIT", 1)
    security._http_requests.clear()
    security._ws_requests.clear()

    ip1 = "1.1.1.1"
    ip2 = "2.2.2.2"
    h1 = {"X-Forwarded-For": ip1, "Authorization": "Token A"}
    h2 = {"X-Forwarded-For": ip2, "Authorization": "Token B"}

    r1 = client.get("/whoami", headers=h1)
    assert r1.status_code == 200
    assert r1.json()["user_id"] == "anon"

    r2 = client.get("/whoami", headers=h1)
    assert r2.status_code == 429

    r3 = client.get("/whoami", headers=h2)
    assert r3.status_code == 200
    assert r3.json()["user_id"] == "anon"
