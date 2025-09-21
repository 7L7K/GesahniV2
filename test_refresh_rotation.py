#!/usr/bin/env python3
import logging
import os

# Set environment for dev auth
os.environ['ENV'] = 'dev'
os.environ['DEV_AUTH'] = '1'

logging.getLogger().setLevel(logging.CRITICAL)

from fastapi.testclient import TestClient
from app.main import app

def test_refresh_rotation():
    with TestClient(app) as c:
        # 1) Login – collect cookies
        login_resp = c.post("/v1/auth/dev/login", json={"user_id":"test","scopes":["chat:write"]}, allow_redirects=False)
        print("Login status:", login_resp.status_code)
        print("Login cookies:", dict(login_resp.cookies))

        # 2) Refresh – with cookie jar attached
        refresh_resp = c.post("/v1/auth/refresh", allow_redirects=False)
        print("Refresh status:", refresh_resp.status_code)

        # 3) Metrics – confirm counter moved
        metrics_resp = c.get("/metrics")
        refresh_lines = [ln for ln in metrics_resp.text.splitlines() if ln.startswith("auth_refresh_rotations_total")]
        print("Refresh rotation metrics:", refresh_lines[:2])

if __name__ == "__main__":
    test_refresh_rotation()
