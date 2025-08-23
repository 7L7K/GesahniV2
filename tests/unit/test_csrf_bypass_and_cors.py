import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.csrf import CSRFMiddleware


def _app():
    os.environ["CSRF_ENABLED"] = "1"
    a = FastAPI()
    a.add_middleware(CSRFMiddleware)

    @a.post("/webhook")
    async def webhook():
        return {"ok": True}

    @a.post("/post")
    async def post():
        return {"ok": True}

    return a


def test_webhook_with_signature_bypasses_csrf():
    c = TestClient(_app())

    # Create a test webhook endpoint in the app
    @c.app.post("/v1/ha/webhook")
    async def test_webhook():
        return {"status": "ok"}

    r = c.post("/v1/ha/webhook", headers={"X-Signature": "sig"})
    assert r.status_code == 200


def test_bearer_token_bypasses_csrf():
    c = TestClient(_app())
    r = c.post("/post", headers={"Authorization": "Bearer token"})
    assert r.status_code == 200


def test_cors_headers_on_404_include_acao():
    # Use real app which has CORS configured
    from app.main import app as real_app

    c = TestClient(real_app)
    r = c.get("/__missing__", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 404
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert r.headers.get("access-control-allow-credentials") in ("true", "True")
