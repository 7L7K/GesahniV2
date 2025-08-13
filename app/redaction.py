from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Tuple, List, Iterable


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


def _normalize_phone(s: str) -> str:
    digits = re.sub(r"\D+", "", s or "")
    # Normalise common US format: drop leading country code '1' for 11‑digit numbers
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _load_phone_whitelist() -> List[str]:
    """Load phone numbers from contacts list for whitelist matching.

    Numbers are normalized to digits-only for comparison.
    """
    try:
        from app.api.contacts import CONTACTS_FILE  # type: ignore
    except Exception:
        CONTACTS_FILE = Path(os.getenv("CONTACTS_FILE", "data/contacts.json"))
    try:
        if CONTACTS_FILE.exists():
            data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8") or "[]")
            nums: List[str] = []
            if isinstance(data, list):
                for item in data:
                    val = (item or {}).get("phone") or (item or {}).get("number")
                    if isinstance(val, str) and val.strip():
                        nums.append(_normalize_phone(val))
            return [n for n in nums if n]
    except Exception:
        return []
    return []


def redact_pii(text: str, *, whitelist_numbers: Iterable[str] | None = None) -> Tuple[str, Dict[str, str]]:
    """Return (redacted_text, mapping) for common PII.

    Mapping keys are placeholder tokens and values are the original strings.
    """

    redactions: Dict[str, str] = {}
    counters = {"EMAIL": 0, "PHONE": 0, "SSN": 0}

    wl: set[str] = set(_normalize_phone(n) for n in (whitelist_numbers or []))

    def _repl(kind: str, value: str) -> str:
        counters[kind] += 1
        key = f"[PII_{kind}_{counters[kind]}]"
        redactions[key] = value
        return key

    # Patterns
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}\b")
    ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    t = email_re.sub(lambda m: _repl("EMAIL", m.group(0)), text or "")
    def _phone_sub(m: re.Match[str]) -> str:
        raw = m.group(0)
        if _normalize_phone(raw) in wl:
            return raw
        return _repl("PHONE", raw)
    t = phone_re.sub(_phone_sub, t)
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
    # Include whitelist numbers from contacts
    redacted, mapping = redact_pii(text, whitelist_numbers=_load_phone_whitelist())
    store_redaction_map(kind, item_id, mapping)
    return redacted


__all__ = [
    "redact_pii",
    "store_redaction_map",
    "get_redaction_map",
    "redact_and_store",
]


