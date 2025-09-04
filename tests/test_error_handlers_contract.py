import subprocess
import time
import requests
import os
import sys
import signal


def _start_server(port: int = 8001):
    # Launch uvicorn in background for the tests using the current Python executable
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:create_app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    env = os.environ.copy()
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for the server to respond on /health (timeout after ~10s)
    deadline = time.time() + 10
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=1)
            if r.status_code in (200, 204, 404):
                return proc
        except requests.exceptions.RequestException:
            time.sleep(0.2)

    # Didn't start in time
    _stop_server(proc)
    raise RuntimeError("uvicorn failed to start in time")


def _stop_server(proc):
    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()


def test_404_envelope_and_headers():
    proc = _start_server()
    try:
        r = requests.get("http://127.0.0.1:8001/nope", timeout=5)
        assert r.status_code == 404
        assert "X-Error-Code" in r.headers
        body = r.json()
        assert "code" in body
        assert body["details"]["status_code"] == 404
        assert body["details"]["path"] == "/nope"
    finally:
        _stop_server(proc)


def test_options_preflight_cors():
    proc = _start_server()
    try:
        r = requests.options("http://127.0.0.1:8001/v1/ask", timeout=5)
        assert r.status_code in (200, 204)
        assert "access-control-expose-headers" in r.headers
    finally:
        _stop_server(proc)


def test_422_validation_contains_legacy_fields():
    proc = _start_server()
    try:
        r = requests.post("http://127.0.0.1:8001/v1/ask", json={"bad": "shape"}, timeout=5)
        assert r.status_code == 422
        assert r.headers.get("X-Error-Code") == "invalid_input"
        body = r.json()
        assert body.get("detail") == "Validation error"
        assert isinstance(body.get("errors"), list)
    finally:
        _stop_server(proc)


