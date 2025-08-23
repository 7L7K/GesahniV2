# app/audit/__init__.py
"""
Phase 6.2: Append-Only Audit Trail System

This package provides structured, immutable audit logging for HTTP and WebSocket operations.
"""

from .models import AuditEvent
from .store import append, bulk, get_audit_file_path, get_audit_file_size

__all__ = [
    "AuditEvent",
    "append",
    "bulk",
    "get_audit_file_path",
    "get_audit_file_size",
]
