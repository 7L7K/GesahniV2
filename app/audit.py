from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict


AUDIT_FILE = Path(os.getenv("AUDIT_LOG", Path(__file__).resolve().parent / "data" / "audit.jsonl"))
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


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


def append_audit(action: str, *, user_id_hashed: str | None = None, data: Dict[str, Any] | None = None) -> str:
    """Append an audit record with a chained hash and return the record hash."""
    prev = _last_hash()
    record = {
        "action": action,
        "user": user_id_hashed,
        "data": data or {},
        "prev": prev,
    }
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    digest = sha256(payload.encode("utf-8")).hexdigest()
    record["hash"] = digest
    with AUDIT_FILE.open("ab") as f:
        f.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
    return digest


__all__ = ["append_audit"]


