"""
Phase 6.2: Legacy audit module preserved as audit_legacy for compatibility.

This file contains the older audit helpers and a compatibility shim that will be
referenced by the new `app.audit` package when the repo needs to fall back to the
legacy behavior.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

# Import new audit system for compatibility
try:
    from app.audit_new.models import AuditEvent
    from app.audit_new.store import append

    NEW_AUDIT_AVAILABLE = True
except ImportError:
    NEW_AUDIT_AVAILABLE = False


# PHASE 6: Enhanced Immutable Audit System
# Make the audit directory and filename configurable to match tests/docs.
# Single source of truth: AUDIT_DIR defaults to `data/audit` and AUDIT_FILE
# defaults to `events.ndjson` inside that directory. Tests can override via
# AUDIT_DIR/AUDIT_FILE environment variables.
AUDIT_DIR = Path(
    os.getenv("AUDIT_DIR", Path(__file__).resolve().parent / "data" / "audit")
)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# Allow overriding the file name (tests expect `events.ndjson`)
AUDIT_FILE = Path(os.getenv("AUDIT_FILE", AUDIT_DIR / "events.ndjson"))
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

# Audit event types for consistency
AUDIT_EVENT_TYPES = {
    # Authentication events
    "auth.login": "User authentication attempt",
    "auth.logout": "User logout",
    "auth.token_refresh": "Access token refresh",
    "auth.unauthorized": "Unauthorized access attempt",
    "auth.scope_denied": "Scope access denied",
    "auth.scope_granted": "Scope access granted",
    "auth.jwt_invalid": "Invalid JWT token",
    "auth.session_expired": "Session expired",
    # User management events
    "user.created": "User account created",
    "user.updated": "User account updated",
    "user.deleted": "User account deleted",
    "user.password_changed": "User password changed",
    "user.profile_accessed": "User profile accessed",
    "user.settings_changed": "User settings changed",
    # Administrative events
    "admin.access": "Administrative function accessed",
    "admin.config_changed": "System configuration changed",
    "admin.user_impersonated": "User impersonation",
    "admin.backup_created": "System backup created",
    "admin.maintenance": "System maintenance performed",
    # Memory and AI events
    "memory.accessed": "Memory data accessed",
    "memory.modified": "Memory data modified",
    "memory.deleted": "Memory data deleted",
    "memory.searched": "Memory search performed",
    "ai.chat_started": "AI chat session started",
    "ai.chat_message": "AI chat message sent",
    "ai.voice_used": "Voice synthesis/recognition used",
    # WebSocket events
    "ws.connect": "WebSocket connection established",
    "ws.disconnect": "WebSocket connection closed",
    "ws.message_sent": "WebSocket message sent",
    "ws.message_received": "WebSocket message received",
    "ws.error": "WebSocket error occurred",
    # API and system events
    "api.request": "API endpoint accessed",
    "api.error": "API error occurred",
    "system.startup": "System startup",
    "system.shutdown": "System shutdown",
    "system.health_check": "Health check performed",
    "rate_limit.hit": "Rate limit exceeded",
    # Security events
    "security.suspicious_activity": "Suspicious activity detected",
    "security.brute_force_attempt": "Brute force attempt detected",
    "security.ip_blocked": "IP address blocked",
    "security.failed_login": "Failed login attempt",
}


def _last_hash() -> str:
    try:
        if not AUDIT_FILE.exists():
            return ""
        with AUDIT_FILE.open("rb") as f:
            try:
                f.seek(-4096, os.SEEK_END)
            except OSError:
                f.seek(0)
            tail = f.read().splitlines()
        if not tail:
            return ""
        last = tail[-1]
        rec = json.loads(last.decode("utf-8"))
        return rec.get("hash", "")
    except Exception:
        return ""


def append_audit(
    action: str,
    *,
    user_id_hashed: str | None = None,
    data: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    websocket_id: str | None = None,
) -> str:
    """Append an immutable audit record with chained hash and return the record hash.

    PHASE 6: Enhanced audit trail with comprehensive metadata for HTTP and WebSocket operations.

    Args:
        action: The audit event type (see AUDIT_EVENT_TYPES)
        user_id_hashed: SHA256 hash of user ID for privacy
        data: Additional event-specific data
        ip_address: Client IP address
        user_agent: User agent string
        session_id: Session identifier
        request_id: HTTP request ID for correlation
        websocket_id: WebSocket connection ID for correlation

    Returns:
        The cryptographic hash of the audit record for integrity verification
    """
    # Use new audit system if available
    if NEW_AUDIT_AVAILABLE:
        try:
            # Map old API to new API
            meta = {
                "legacy_action": action,
                "user_id_hashed": user_id_hashed,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "session_id": session_id,
                "websocket_id": websocket_id,
            }

            # Merge data into meta
            if data:
                meta.update(data)

            # Create new audit event
            event = AuditEvent(
                user_id=user_id_hashed,
                route=action,  # Use action as route for now
                method="API",  # Default method
                status=200,  # Default status
                ip=ip_address,
                req_id=request_id,
                scopes=[],  # No scope info in old API
                action=action,
                meta=meta,
            )

            # Append to new audit system
            append(event)
            return f"new_audit_{event.ts.isoformat()}"

        except Exception:
            # Fall back to old system if new system fails
            pass

    # Fallback to old audit system
    prev_hash = _last_hash()
    timestamp = datetime.now(UTC).isoformat()

    # Create comprehensive audit record
    record = {
        "action": action,
        "timestamp": timestamp,
        "user": user_id_hashed,
        "data": data or {},
        "metadata": {
            "ip_address": ip_address,
            "user_agent": user_agent,
            "session_id": session_id,
            "request_id": request_id,
            "websocket_id": websocket_id,
            "audit_version": "2.0",  # For future compatibility
        },
        "prev_hash": prev_hash,
    }

    # Create deterministic payload for hashing (excluding the hash itself)
    payload = json.dumps(
        record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    record["hash"] = digest

    # Write to append-only audit log
    with AUDIT_FILE.open("ab") as f:
        f.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))

    return digest


def append_ws_audit(
    websocket_id: str,
    action: str,
    *,
    user_id_hashed: str | None = None,
    data: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """WebSocket-specific audit logging with connection correlation."""
    return append_audit(
        action,
        user_id_hashed=user_id_hashed,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
        websocket_id=websocket_id,
    )


def append_http_audit(
    request_id: str,
    action: str,
    *,
    user_id_hashed: str | None = None,
    data: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_id: str | None = None,
) -> str:
    """HTTP-specific audit logging with request correlation."""
    return append_audit(
        action,
        user_id_hashed=user_id_hashed,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id,
        request_id=request_id,
    )


def verify_audit_integrity() -> tuple[bool, list[str]]:
    """Verify the integrity of the audit log using chained hashes.

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    if not AUDIT_FILE.exists():
        return True, issues  # Empty log is valid

    try:
        with AUDIT_FILE.open("r") as f:
            lines = f.readlines()

        if not lines:
            return True, issues

        prev_hash = ""
        for i, line in enumerate(lines):
            try:
                record = json.loads(line.strip())

                # Verify chain
                if record.get("prev_hash") != prev_hash:
                    issues.append(f"Line {i+1}: Hash chain broken")

                # Verify record integrity
                record_hash = record.pop("hash", None)
                payload = json.dumps(
                    record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                )
                calculated_hash = sha256(payload.encode("utf-8")).hexdigest()

                if record_hash != calculated_hash:
                    issues.append(f"Line {i+1}: Record integrity check failed")

                # Restore hash for next iteration
                record["hash"] = record_hash
                prev_hash = record_hash

            except json.JSONDecodeError:
                issues.append(f"Line {i+1}: Invalid JSON")
            except Exception as e:
                issues.append(f"Line {i+1}: {str(e)}")

    except Exception as e:
        issues.append(f"File read error: {str(e)}")
        return False, issues

    return len(issues) == 0, issues


def get_audit_events(
    limit: int = 100,
    since_timestamp: str | None = None,
    action_filter: str | None = None,
    user_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Query audit events with filtering and pagination.

    PHASE 6: Queryable audit trail for compliance and debugging.
    """
    if not AUDIT_FILE.exists():
        return []

    events = []
    try:
        with AUDIT_FILE.open("r") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())

                    # Apply filters
                    if (
                        since_timestamp
                        and record.get("timestamp", "") < since_timestamp
                    ):
                        continue
                    if action_filter and record.get("action") != action_filter:
                        continue
                    if user_filter and record.get("user") != user_filter:
                        continue

                    events.append(record)

                    if len(events) >= limit:
                        break

                except json.JSONDecodeError:
                    continue  # Skip malformed lines

    except Exception:
        return []

    return events


__all__ = [
    "append_audit",
    "append_ws_audit",
    "append_http_audit",
    "verify_audit_integrity",
    "get_audit_events",
    "AUDIT_EVENT_TYPES",
]
