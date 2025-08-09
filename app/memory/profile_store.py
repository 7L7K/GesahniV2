from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import RLock
from typing import Any, Dict


class ProfileStore:
    """In-memory profile snapshot with TTL and periodic persistence.

    The store keeps a per-user dict of profile attributes (e.g., preferences
    like night_temp) with a TTL for the in-memory cache. A background job can
    call ``persist_all`` hourly to write a compact JSON snapshot to disk.
    """

    def __init__(self, ttl_seconds: int = 3600, path: str | None = None) -> None:
        self._ttl = ttl_seconds
        base = Path(os.getenv("PROFILE_DB", Path(__file__).resolve().parent.parent / "data" / "profiles.json"))
        self._path = Path(base)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._mem: Dict[str, Dict[str, Any]] = {}
        self._exp: Dict[str, float] = {}
        self._lock = RLock()
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._mem = data
            except Exception:
                self._mem = {}

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._mem, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def get(self, user_id: str) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            exp = self._exp.get(user_id, 0.0)
            if exp and now > exp:
                # expired snapshot; keep persisted copy for next get
                self._mem.pop(user_id, None)
                self._exp.pop(user_id, None)
            return dict(self._mem.get(user_id, {}))

    def set(self, user_id: str, key: str, value: Any) -> None:
        with self._lock:
            profile = self._mem.setdefault(user_id, {})
            profile[key] = value
            self._exp[user_id] = time.time() + self._ttl

    def update(self, user_id: str, attrs: Dict[str, Any]) -> None:
        with self._lock:
            profile = self._mem.setdefault(user_id, {})
            profile.update(attrs)
            self._exp[user_id] = time.time() + self._ttl

    def persist_all(self) -> None:
        with self._lock:
            self._save()


profile_store = ProfileStore()

__all__ = ["ProfileStore", "profile_store"]


