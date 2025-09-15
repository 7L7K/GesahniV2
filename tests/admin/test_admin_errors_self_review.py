import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_admin_errors_and_self_review():
    os.environ["ADMIN_TOKEN"] = "t"
    from app.api.admin import router as admin_router

    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    client = TestClient(app)

    # errors
    r = client.get("/v1/admin/errors?token=t")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict) and "errors" in body

    # self review
    r2 = client.get("/v1/admin/self_review?token=t")
    assert r2.status_code == 200
    assert isinstance(r2.json(), dict)
