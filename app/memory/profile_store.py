from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, Optional


logger = logging.getLogger(__name__)


CANONICAL_KEYS: tuple[str, ...] = (
    "preferred_name",
    "favorite_color",
    "timezone",
    "locale",
    "home_city",
    "clothing_sizes",
    "music_service",
    "commute_home",
    "device_ids",
    "calendars_connected",
)


class ProfileStore:
    """Authoritative KV profile store with upsert semantics and audit logging."""

    def __init__(self, ttl_seconds: int = 3600, path: str | None = None) -> None:
        self._ttl = ttl_seconds
        base = Path(
            os.getenv(
                "PROFILE_DB",
                Path(__file__).resolve().parent.parent / "data" / "profiles.json",
            )
        )
        self._path = Path(base)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # { user_id: { key: {"value": Any, "updated_at": float, "source": str} } }
        self._mem: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._exp: Dict[str, float] = {}
        self._lock = RLock()
        self._last_key: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    fixed: Dict[str, Dict[str, Dict[str, Any]]] = {}
                    now = time.time()
                    for uid, attrs in data.items():
                        if isinstance(attrs, dict):
                            fixed[uid] = {}
                            for k, v in attrs.items():
                                if isinstance(v, dict) and ("value" in v and "updated_at" in v):
                                    fixed[uid][k] = v
                                else:
                                    fixed[uid][k] = {"value": v, "updated_at": now, "source": "import"}
                    self._mem = fixed
            except Exception:
                self._mem = {}

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._mem, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _refresh_ttl(self, user_id: str) -> None:
        self._exp[user_id] = time.time() + self._ttl

    def _expired(self, user_id: str) -> bool:
        exp = self._exp.get(user_id, 0.0)
        return bool(exp and time.time() > exp)

    # ---------------- Public API ----------------
    def get_snapshot(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if self._expired(user_id):
                self._mem.pop(user_id, None)
                self._exp.pop(user_id, None)
            return dict(self._mem.get(user_id, {}))

    def get_values(self, user_id: str, keys: Iterable[str] | None = None) -> Dict[str, Any]:
        snap = self.get_snapshot(user_id)
        out: Dict[str, Any] = {}
        for k, rec in snap.items():
            if keys is None or k in keys:
                out[k] = rec.get("value")
        return out

    def get_value(self, user_id: str, key: str) -> Any | None:
        return self.get_values(user_id, keys=[key]).get(key)

    def upsert(self, user_id: str, key: str, value: Any, *, source: str = "utterance") -> Dict[str, Any]:
        if key not in CANONICAL_KEYS:
            logger.warning("profile_store: non-canonical key %s", key)
        now = time.time()
        with self._lock:
            user = self._mem.setdefault(user_id, {})
            prev = user.get(key)
            if prev is None or float(prev.get("updated_at", 0.0) or 0.0) <= now:
                user[key] = {"value": value, "updated_at": now, "source": source}
            self._refresh_ttl(user_id)
            rec = dict(user[key])
        try:
            logger.info(
                "profile_fact upsert — key=%s value=%r user=%s source=%s updated_at=%s",
                key,
                value,
                user_id,
                source,
                int(rec.get("updated_at", now)),
            )
        except Exception:
            pass
        return rec

    def set_last_asked_key(self, user_id: str, key: Optional[str]) -> None:
        with self._lock:
            if key:
                self._last_key[user_id] = key
            else:
                self._last_key.pop(user_id, None)

    def get_last_asked_key(self, user_id: str) -> Optional[str]:
        with self._lock:
            return self._last_key.get(user_id)

    def update_bulk(self, user_id: str, attrs: Dict[str, Any], *, source: str = "import") -> None:
        with self._lock:
            for k, v in (attrs or {}).items():
                self.upsert(user_id, k, v, source=source)
            self._refresh_ttl(user_id)

    def persist_all(self) -> None:
        with self._lock:
            self._save()

    # Legacy convenience
    def get(self, user_id: str) -> Dict[str, Any]:
        return self.get_values(user_id)


profile_store = ProfileStore()

__all__ = ["ProfileStore", "profile_store", "CANONICAL_KEYS"]


