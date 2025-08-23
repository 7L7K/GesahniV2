"""
Phase 6.5.b: Audit Trail Tests
Tests that audit events are properly appended to NDJSON file
"""

import json
import os
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app


def get_audit_file_path():
    """Get the actual audit file path used by the system"""
    # Use the same logic as the audit system
    audit_dir = Path(os.getenv("AUDIT_DIR", "data/audit"))
    audit_file = Path(os.getenv("AUDIT_FILE", audit_dir / "events.ndjson"))
    return audit_file


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


def _create_auth_token(scopes=None, sub="test-user-123"):
    """Create a JWT token for testing"""
    key = os.environ.get("JWT_SECRET", "test-secret-key-for-jwt-tokens-in-tests")
    now = int(time.time())
    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + 300,  # 5 minutes
    }
    if scopes is not None:
        payload["scopes"] = scopes
    return jwt.encode(payload, key, algorithm="HS256")


@pytest.fixture
def tmp_audit_dir(tmp_path, monkeypatch):
    """Temporary audit directory for testing"""
    audit_dir = tmp_path / "audit"
    audit_file = audit_dir / "events.ndjson"
    monkeypatch.setenv("AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("AUDIT_FILE", str(audit_file))
    return audit_dir


def test_audit_file_created_on_request(client, tmp_audit_dir):
    """Test that audit file is created when requests are made"""
    # Make a request to trigger audit logging
    response = client.get("/healthz")
    assert response.status_code == 200

    # Check the actual audit file location
    audit_file_path = get_audit_file_path()
    assert audit_file_path.exists(), f"Audit file should exist at {audit_file_path}"


def test_audit_append_basic_structure(client, tmp_audit_dir):
    """Test basic structure of audit events"""
    # Make a request
    response = client.get("/healthz")
    assert response.status_code == 200

    # Read audit file
    audit_file = get_audit_file_path()
    assert audit_file.exists()

    content = audit_file.read_text().strip()
    assert content, "Audit file should not be empty"

    lines = content.split("\n")
    assert len(lines) >= 1, "Should have at least one audit event"

    # Find the event for our specific request (GET /healthz)
    target_event = None
    for line in reversed(lines):  # Search from most recent backwards
        try:
            event = json.loads(line)
            # Look for the healthz request event
            if (
                event.get("action") == "http_request"
                and event.get("method") == "GET"
                and event.get("status") == 200
                and (
                    event.get("route") == "healthz"
                    or "/healthz" in event.get("meta", {}).get("path", "")
                )
            ):
                target_event = event
                break
        except json.JSONDecodeError:
            continue

    assert (
        target_event is not None
    ), f"Could not find healthz request event in audit log. Found {len(lines)} total events"

    # Verify required fields
    assert "ts" in target_event
    assert "route" in target_event
    assert "method" in target_event
    assert "status" in target_event
    assert "action" in target_event

    # Verify specific values
    assert target_event["action"] == "http_request"
    assert target_event["method"] == "GET"
    assert target_event["status"] == 200


def test_audit_append_multiple_events(client, tmp_audit_dir):
    """Test that multiple requests create multiple audit events"""
    # Make multiple requests
    client.get("/healthz")
    client.get("/v1/admin/metrics")
    client.post("/v1/admin/config", json={"test": "data"})

    # Read audit file
    audit_file = tmp_audit_dir / "events.ndjson"
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    # Should have multiple events
    assert len(lines) >= 3, f"Expected at least 3 events, got {len(lines)}"

    # Parse all events
    events = [json.loads(line) for line in lines]

    # Verify events are in order
    methods = [event["method"] for event in events]
    assert "GET" in methods
    assert "POST" in methods


def test_audit_append_with_error_status(client, tmp_audit_dir):
    """Test audit logging for error responses"""
    # Make a request that will result in an error
    response = client.get("/nonexistent-endpoint")
    assert response.status_code == 404

    # Read audit file
    audit_file = tmp_audit_dir / "events.ndjson"
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    # Find the 404 event
    events = [json.loads(line) for line in lines]
    error_events = [e for e in events if e.get("status") == 404]

    assert len(error_events) >= 1, "Should have at least one 404 event"
    error_event = error_events[-1]

    assert error_event["status"] == 404
    assert error_event["action"] == "http_request"


def test_audit_append_preserves_history(client, tmp_audit_dir):
    """Test that audit file preserves history across requests"""
    # Make first request
    client.get("/healthz")
    audit_file = tmp_audit_dir / "events.ndjson"
    content1 = audit_file.read_text().strip()
    lines1 = content1.split("\n")

    # Make second request
    client.get("/v1/admin/metrics")
    content2 = audit_file.read_text().strip()
    lines2 = content2.split("\n")

    # Should have more lines
    assert len(lines2) > len(lines1), "Should preserve and append to history"


def test_audit_append_timestamp_format(client, tmp_audit_dir):
    """Test that timestamps are in proper ISO format"""
    import re

    client.get("/healthz")

    audit_file = tmp_audit_dir / "events.ndjson"
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    last_event = json.loads(lines[-1])

    # ISO format: 2024-01-01T12:00:00.123456 or similar
    iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    assert re.match(
        iso_pattern, last_event["ts"]
    ), f"Invalid ISO timestamp: {last_event['ts']}"


def test_audit_append_includes_request_details(client, tmp_audit_dir):
    """Test that audit events include detailed request information"""
    # Make a request with specific characteristics and proper authentication
    token = _create_auth_token(scopes=["admin:read"])
    response = client.get(
        "/v1/admin/metrics?param=test", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200

    audit_file = tmp_audit_dir / "events.ndjson"
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    last_event = json.loads(lines[-1])

    # Should include path information
    assert "path" in last_event["meta"] or "route" in last_event
    assert last_event["method"] == "GET"


def test_audit_append_with_authentication(client, tmp_audit_dir):
    """Test audit logging with authentication context"""
    # This would need a valid token in a real scenario
    # For now, test with invalid token to see auth-related fields
    response = client.get(
        "/v1/admin/config", headers={"Authorization": "Bearer invalid-token"}
    )

    audit_file = tmp_audit_dir / "events.ndjson"
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    last_event = json.loads(lines[-1])

    # Should still log even with auth issues
    assert last_event["action"] == "http_request"
    assert last_event["status"] in [401, 403]  # Auth failure


def test_audit_append_file_permissions(client, tmp_audit_dir):
    """Test that audit file has appropriate permissions"""
    client.get("/healthz")

    audit_file = tmp_audit_dir / "events.ndjson"
    assert audit_file.exists()

    # Check file permissions (should be readable)
    assert audit_file.stat().st_mode & 0o400, "Audit file should be readable"

    # Verify we can read it
    content = audit_file.read_text()
    assert content, "Should be able to read audit file"


def test_audit_append_concurrent_access(client, tmp_audit_dir):
    """Test audit file handling under concurrent access"""
    import concurrent.futures

    def make_request():
        return client.get("/healthz")

    # Make concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(10)]
        responses = [f.result() for f in concurrent.futures.as_completed(futures)]

    # All should succeed
    assert all(r.status_code == 200 for r in responses)

    # Check audit file
    audit_file = get_audit_file_path()
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    # Should have all events
    assert len(lines) >= 10, f"Expected at least 10 audit events, got {len(lines)}"

    # All should be valid JSON
    events = [json.loads(line) for line in lines]
    assert all(event["action"] == "http_request" for event in events)


def test_audit_append_file_rotation_scenario(client, tmp_audit_dir):
    """Test audit file behavior (in a real system, this would test log rotation)"""
    # Make many requests to simulate file growth
    for i in range(100):
        client.get("/healthz")

    audit_file = tmp_audit_dir / "events.ndjson"
    content = audit_file.read_text().strip()
    lines = content.split("\n")

    # Should have all events
    assert len(lines) >= 100, f"Expected at least 100 audit events, got {len(lines)}"

    # File size should be reasonable
    file_size = audit_file.stat().st_size
    assert file_size > 0, "Audit file should not be empty"
    assert file_size < 10 * 1024 * 1024, "Audit file should not be excessively large"
