from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Tuple


# Base directory for redaction maps; stored out-of-band from primary data
REDACTIONS_DIR = Path(
    os.getenv(
        "REDACTIONS_DIR",
        Path(__file__).resolve().parent.parent / "data" / "redactions",
    )
)
REDACTIONS_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_segment(seg: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", seg)[:256]


def _map_path(kind: str, item_id: str) -> Path:
    k = _sanitize_segment(kind or "misc")
    i = _sanitize_segment(item_id or "unknown")
    base = REDACTIONS_DIR / k
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{i}.json"


def redact_pii(text: str) -> Tuple[str, Dict[str, str]]:
    """Return (redacted_text, mapping) for common PII.

    Mapping keys are placeholder tokens and values are the original strings.
    """

    redactions: Dict[str, str] = {}
    counters = {"EMAIL": 0, "PHONE": 0, "SSN": 0}

    def _repl(kind: str, value: str) -> str:
        counters[kind] += 1
        key = f"[PII_{kind}_{counters[kind]}]"
        redactions[key] = value
        return key

    # Patterns
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(
        r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}\b"
    )
    ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    t = email_re.sub(lambda m: _repl("EMAIL", m.group(0)), text or "")
    t = phone_re.sub(lambda m: _repl("PHONE", m.group(0)), t)
    t = ssn_re.sub(lambda m: _repl("SSN", m.group(0)), t)
    return t, redactions


def store_redaction_map(kind: str, item_id: str, mapping: Dict[str, str]) -> None:
    """Persist mapping at a separate, access-controlled path.

    Merges with an existing map if present.
    """

    if not mapping:
        return
    path = _map_path(kind, item_id)
    try:
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    existing.update(mapping)
                    mapping = existing
            except Exception:
                pass
        path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    except Exception:
        # Best-effort; failures here must not break request handling
        return


def get_redaction_map(kind: str, item_id: str) -> Dict[str, str]:
    path = _map_path(kind, item_id)
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def redact_and_store(kind: str, item_id: str, text: str) -> str:
    redacted, mapping = redact_pii(text)
    store_redaction_map(kind, item_id, mapping)
    return redacted


__all__ = [
    "redact_pii",
    "store_redaction_map",
    "get_redaction_map",
    "redact_and_store",
]


