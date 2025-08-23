import asyncio
import os

from fastapi.testclient import TestClient


def _mk_app():
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    from app.main import app

    return app


def test_stream_cancels_cleanly(monkeypatch):
    app = _mk_app()
    client = TestClient(app)

    # Monkeypatch router.route_prompt to stream a few chunks slowly
    import app.main as main_mod

    async def _fake_route(prompt, model_override, user_id, stream_cb=None):
        for i in range(3):
            await asyncio.sleep(0.01)
            if stream_cb:
                await stream_cb(f"tok{i}")
        return "done"

    monkeypatch.setattr(main_mod, "route_prompt", _fake_route)

    with client.stream("POST", "/v1/ask", json={"prompt": "hi"}) as resp:
        assert resp.status_code == 200
        # Read only first chunk and then break (simulate client disconnect)
        next(resp.iter_text())
        # context manager exit will cancel the response stream; no exception expected


