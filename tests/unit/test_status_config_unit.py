from fastapi.testclient import TestClient


def test_config_endpoint_includes_env_defaults():
    from app.main import app

    c = TestClient(app)
    r = c.get("/v1/config")
    assert r.status_code in (200, 403)
    # When accessible, it includes SIM_THRESHOLD and RETRIEVE_POLICY defaults
    if r.status_code == 200:
        body = r.json()
        assert "SIM_THRESHOLD" in body
        assert "RETRIEVE_POLICY" in body
