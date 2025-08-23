# app/audit/store.py
import os
from collections.abc import Iterable
from pathlib import Path

from app.audit.models import AuditEvent


# Single source of truth:
def _resolve_audit_file() -> Path:
    audit_dir = Path(os.getenv("AUDIT_DIR", "data/audit"))
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = Path(os.getenv("AUDIT_FILE", audit_dir / "events.ndjson"))
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    return audit_file


def append(event: AuditEvent) -> None:
    """Append a single audit event to the append-only log."""
    audit_file = _resolve_audit_file()
    line = event.model_dump_json()
    with audit_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def bulk(events: Iterable[AuditEvent]) -> None:
    """Append multiple audit events to the append-only log."""
    audit_file = _resolve_audit_file()
    with audit_file.open("a", encoding="utf-8") as f:
        for ev in events:
            f.write(ev.model_dump_json() + "\n")


def get_audit_file_path() -> Path:
    """Get the path to the audit log file."""
    return _resolve_audit_file()


def get_audit_file_size() -> int:
    """Get the current size of the audit log file in bytes."""
    audit_file = _resolve_audit_file()
    if audit_file.exists():
        return audit_file.stat().st_size
    return 0
