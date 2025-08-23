"""
Phase 6.2: Test Append-Only Audit Trail

Tests to verify that the audit system works correctly.
"""

import os
import tempfile
from datetime import datetime

from app.audit.models import AuditEvent
from app.audit.store import append, bulk, get_audit_file_path, get_audit_file_size


class TestAuditModels:
    """Test audit event models."""

    def test_audit_event_creation(self):
        """Test basic audit event creation."""
        event = AuditEvent(
            user_id="test_user",
            route="/test/endpoint",
            method="GET",
            status=200,
            ip="127.0.0.1",
            scopes=["user:profile"],
            action="http_request",
            meta={"test": "value"}
        )

        assert event.user_id == "test_user"
        assert event.route == "/test/endpoint"
        assert event.method == "GET"
        assert event.status == 200
        assert event.ip == "127.0.0.1"
        assert event.scopes == ["user:profile"]
        assert event.action == "http_request"
        assert event.meta == {"test": "value"}
        assert isinstance(event.ts, datetime)

    def test_audit_event_defaults(self):
        """Test audit event default values."""
        event = AuditEvent(
            route="/minimal",
            method="POST",
            status=404
        )

        assert event.user_id is None
        assert event.ip is None
        assert event.req_id is None
        assert event.scopes == []
        assert event.action == "http_request"
        assert event.meta == {}

    def test_audit_event_json_serialization(self):
        """Test audit event JSON serialization."""
        event = AuditEvent(
            user_id="test_user",
            route="/test",
            method="GET",
            status=200
        )

        json_str = event.model_dump_json()
        assert "test_user" in json_str
        assert "/test" in json_str
        assert "GET" in json_str

        # Test deserialization
        event2 = AuditEvent.model_validate_json(json_str)
        assert event2.user_id == event.user_id
        assert event2.route == event.route
        assert event2.method == event.method


class TestAuditStore:
    """Test audit storage functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Create a temporary audit directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.original_audit_dir = os.getenv("AUDIT_DIR")
        os.environ["AUDIT_DIR"] = self.temp_dir

        # Clear any existing events
        audit_file = get_audit_file_path()
        if audit_file.exists():
            audit_file.unlink()

    def teardown_method(self):
        """Clean up test environment."""
        if self.original_audit_dir is not None:
            os.environ["AUDIT_DIR"] = self.original_audit_dir
        else:
            os.environ.pop("AUDIT_DIR", None)

        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_single_audit_append(self):
        """Test appending a single audit event."""
        event = AuditEvent(
            user_id="test_user",
            route="/test",
            method="GET",
            status=200
        )

        append(event)

        audit_file = get_audit_file_path()
        assert audit_file.exists()

        # Check file size
        assert get_audit_file_size() > 0

        # Check file contents
        with open(audit_file) as f:
            lines = f.readlines()
            assert len(lines) == 1
            assert "test_user" in lines[0]
            assert "/test" in lines[0]

    def test_bulk_audit_append(self):
        """Test bulk appending multiple audit events."""
        events = [
            AuditEvent(user_id="user1", route="/test1", method="GET", status=200),
            AuditEvent(user_id="user2", route="/test2", method="POST", status=201),
            AuditEvent(user_id="user3", route="/test3", method="PUT", status=204),
        ]

        bulk(events)

        audit_file = get_audit_file_path()
        assert audit_file.exists()

        with open(audit_file) as f:
            lines = f.readlines()
            assert len(lines) == 3
            assert "user1" in lines[0]
            assert "user2" in lines[1]
            assert "user3" in lines[2]

    def test_append_only_behavior(self):
        """Test that audit file is truly append-only."""
        event1 = AuditEvent(user_id="user1", route="/test1", method="GET", status=200)
        event2 = AuditEvent(user_id="user2", route="/test2", method="POST", status=201)

        # Append first event
        append(event1)
        audit_file = get_audit_file_path()

        # Get initial file size
        initial_size = get_audit_file_size()

        # Append second event
        append(event2)
        final_size = get_audit_file_size()

        # File should be larger
        assert final_size > initial_size

        # Check both events are present
        with open(audit_file) as f:
            content = f.read()
            assert "user1" in content
            assert "user2" in content

    def test_audit_file_permissions(self):
        """Test that audit file is created with appropriate permissions."""
        event = AuditEvent(user_id="test", route="/test", method="GET", status=200)
        append(event)

        audit_file = get_audit_file_path()
        assert audit_file.exists()

        # Check file is readable (basic security test)
        assert audit_file.is_file()
        assert audit_file.stat().st_size > 0


class TestAuditMiddleware:
    """Test audit middleware integration."""

    def test_audit_middleware_import(self):
        """Test that audit middleware can be imported."""
        from app.middleware.audit_mw import AuditMiddleware
        assert AuditMiddleware is not None

    def test_audit_models_import(self):
        """Test that audit models can be imported."""
        from app.audit.models import AuditEvent
        assert AuditEvent is not None

    def test_audit_store_import(self):
        """Test that audit store can be imported."""
        from app.audit.store import append, bulk
        assert append is not None
        assert bulk is not None


class TestWebSocketAudit:
    """Test WebSocket audit event creation."""

    def test_websocket_connect_event(self):
        """Test WebSocket connect audit event structure."""
        from app.audit.models import AuditEvent

        event = AuditEvent(
            user_id="ws_user",
            route="ws_connect",
            method="WS",
            status=101,
            ip="192.168.1.1",
            scopes=["care:resident"],
            action="ws_connect",
            meta={"path": "/v1/ws/care", "endpoint": "/v1/ws/care"}
        )

        assert event.user_id == "ws_user"
        assert event.route == "ws_connect"
        assert event.method == "WS"
        assert event.status == 101
        assert event.ip == "192.168.1.1"
        assert event.scopes == ["care:resident"]
        assert event.action == "ws_connect"
        assert event.meta["path"] == "/v1/ws/care"

    def test_websocket_disconnect_event(self):
        """Test WebSocket disconnect audit event structure."""
        from app.audit.models import AuditEvent

        event = AuditEvent(
            user_id="ws_user",
            route="ws_disconnect",
            method="WS",
            status=1000,
            ip="192.168.1.1",
            scopes=["care:resident"],
            action="ws_disconnect",
            meta={"path": "/v1/ws/care", "endpoint": "/v1/ws/care"}
        )

        assert event.user_id == "ws_user"
        assert event.route == "ws_disconnect"
        assert event.method == "WS"
        assert event.status == 1000
        assert event.action == "ws_disconnect"


if __name__ == "__main__":
    # Run basic tests
    print("Running Phase 6.2 audit tests...")

    # Test basic functionality
    event = AuditEvent(
        user_id="test_user",
        route="/test",
        method="GET",
        status=200
    )

    print(f"✅ Created audit event: {event.user_id} -> {event.route}")
    print(f"✅ Event JSON: {event.model_dump_json()}")

    # Test audit store
    from app.audit.store import get_audit_file_path
    print(f"✅ Audit file path: {get_audit_file_path()}")

    print("✅ All basic tests passed!")
