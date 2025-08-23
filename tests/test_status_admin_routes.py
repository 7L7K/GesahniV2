import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_status_routes_bound_and_json_stable(monkeypatch):
    os.environ["ADMIN_TOKEN"] = "T"
    from app import status
    from app.api.admin import router as admin_router

    app = FastAPI()
    app.include_router(status.router, prefix="/v1")
    app.include_router(admin_router, prefix="/v1")
    client = TestClient(app)

    # /admin/metrics now lives under admin router
    r = client.get("/v1/admin/metrics?token=T")
    assert r.status_code == 200
    assert "metrics" in r.json()

    # /config guarded (status router)
    assert client.get("/v1/config?token=X").status_code == 403
    assert client.get("/v1/config?token=T").status_code == 200


