import sys

from starlette.testclient import TestClient

# 1) create_app must exist and mount everything
try:
    from app.main import create_app
except Exception as e:
    print("FAIL: app.main.create_app not importable:", e)
    sys.exit(1)

app = create_app()
c = TestClient(app)

# 2) Alias/compat targets & contract responses
CASES = [
    ("GET", "/v1/whoami", {200, 401}),
    ("GET", "/v1/spotify/status", {200}),
    ("GET", "/v1/google/status", {200}),
    ("GET", "/v1/calendar/list", {200}),
    ("GET", "/v1/calendar/next", {200}),
    ("GET", "/v1/calendar/today", {200}),
    ("GET", "/v1/care/device_status", {200}),
    ("GET", "/v1/music", {200}),
    ("GET", "/v1/music/devices", {200}),
    ("PUT", "/v1/music/device", {200, 400}),
    ("POST", "/v1/transcribe/abc", {202}),
    ("POST", "/v1/tts/speak", {202, 400}),
    ("POST", "/v1/admin/reload_env", {200, 403}),
    ("POST", "/v1/admin/self_review", {501, 403}),
    ("POST", "/v1/admin/vector_store/bootstrap", {202, 403}),
]

ok = True
for method, path, allowed in CASES:
    r = c.request(method, path, json={"text": "hi", "device_id": "x"})
    good = r.status_code in allowed and isinstance(r.json(), dict)
    print(
        f"{'PASS' if good else 'FAIL'} {method} {path} -> {r.status_code} {r.json() if not good else ''}"
    )
    ok &= good

# 3) OPTIONS autoreply sanity (should be 204, headers from CORS middleware if present)
r = c.options("/v1/whoami")
opt = r.status_code in (200, 204)
print(f"{'PASS' if opt else 'FAIL'} OPTIONS /v1/whoami -> {r.status_code}")

sys.exit(0 if ok and opt else 2)
