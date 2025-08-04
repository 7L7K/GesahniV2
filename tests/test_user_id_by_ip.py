from hashlib import sha256

from fastapi import Depends
from fastapi.testclient import TestClient

from app.deps.user import get_current_user_id
from app.main import app


@app.get("/whoami")
async def whoami(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id}


def test_unauthenticated_requests_from_different_ips_have_distinct_ids():
    client = TestClient(app)
    ip1 = "1.1.1.1"
    ip2 = "2.2.2.2"
    r1 = client.get("/whoami", headers={"X-Forwarded-For": ip1})
    r2 = client.get("/whoami", headers={"X-Forwarded-For": ip2})
    uid1 = r1.json()["user_id"]
    uid2 = r2.json()["user_id"]
    assert uid1 == sha256(ip1.encode("utf-8")).hexdigest()[:12]
    assert uid2 == sha256(ip2.encode("utf-8")).hexdigest()[:12]
    assert uid1 != uid2
