import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_admin_decisions_shape(monkeypatch):
    os.environ["ADMIN_TOKEN"] = "t"
    from app.api.admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    client = TestClient(app)

    # With wrong token forbidden
    assert client.get("/v1/admin/router/decisions?token=x").status_code == 403
    # With correct token OK and stable shape
    resp = client.get("/v1/admin/router/decisions?token=t")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict) and "items" in body and isinstance(body["items"], list)


