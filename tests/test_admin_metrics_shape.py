import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_admin_metrics_shape():
    os.environ["ADMIN_TOKEN"] = "t"
    from app.api.admin import router as admin_router

    app = FastAPI()
    app.include_router(admin_router, prefix="/v1")
    client = TestClient(app)

    r = client.get("/v1/admin/metrics?token=t")
    assert r.status_code == 200
    body = r.json()
    assert "metrics" in body and isinstance(body["metrics"], dict)
    assert "cache_hit_rate" in body
    assert "latency_p95_ms" in body
    assert "transcribe_error_rate" in body
    assert "top_skills" in body and isinstance(body["top_skills"], list)
