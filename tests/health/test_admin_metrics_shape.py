import os


def test_admin_metrics_shape(monkeypatch):
    os.environ["ADMIN_TOKEN"] = "t"
    # Call the handler directly to validate response shape without auth plumbing
    # Directly invoke coroutine with a dummy user id
    import asyncio

    from app.api import admin as admin_api

    body = asyncio.get_event_loop().run_until_complete(
        admin_api.admin_metrics(user_id="admin_user")  # type: ignore[arg-type]
    )
    assert "metrics" in body and isinstance(body["metrics"], dict)
    assert "cache_hit_rate" in body
    assert "latency_p95_ms" in body
    assert "transcribe_error_rate" in body
    assert "top_skills" in body and isinstance(body["top_skills"], list)
