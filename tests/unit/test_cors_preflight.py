from fastapi.testclient import TestClient

from app.main import create_app


def test_cors_preflight_allows_options():
    app = create_app()
    client = TestClient(app)
    r = client.options(
        "/v1/ask",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code in (200, 204)
    # Starlette's CORS middleware varies; check presence (not exact values)
    assert "access-control-allow-origin" in {k.lower(): v for k, v in r.headers.items()}
