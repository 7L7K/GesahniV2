import os
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_admin_retrieval_last():
    os.environ["ADMIN_TOKEN"] = "t"
    from app.api.admin import router as admin_router
    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    client = TestClient(app)
    r = client.get("/v1/admin/retrieval/last?limit=3&token=t")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict) and "items" in data


