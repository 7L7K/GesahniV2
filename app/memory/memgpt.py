from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from textwrap import shorten
from typing import Any, Dict, List
import hashlib
import time


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Compute the Jaro-Winkler similarity between two strings."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    s1_len, s2_len = len(s1), len(s2)
    match_distance = max(s1_len, s2_len) // 2 - 1

    s1_matches = [False] * s1_len
    s2_matches = [False] * s2_len
    matches = 0

    for i in range(s1_len):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, s2_len)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = s2_matches[j] = True
            matches += 1
            break

    if not matches:
        return 0.0

    k = 0
    transpositions = 0
    for i in range(s1_len):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions /= 2

    jaro = (
        matches / s1_len
        + matches / s2_len
        + (matches - transpositions) / matches
    ) / 3

    prefix = 0
    for i in range(min(4, s1_len, s2_len)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + 0.1 * prefix * (1 - jaro)


class MemGPT:
    """Simple in-process memory manager.

    The class stores prompt/answer pairs per session in a JSON file and can
    return condensed session summaries or interactions that match a prompt.
    """

    def __init__(self, storage_path: str | Path | None = None, ttl_seconds: int = 60 * 60 * 24 * 30) -> None:
        """Create a memory manager.

        ``ttl_seconds`` controls how long memories are kept during nightly
        maintenance. The default keeps data for ~30 days.
        """

        self.storage_path = Path(
            storage_path
            or Path(__file__).resolve().parent.parent / "data" / "memories.json"
        )
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        # Dedicated store for pinned memories
        self._pin_store: Dict[str, List[Dict[str, Any]]] = {}
        # Separate file so pins survive across restarts
        self._pin_path = self.storage_path.with_name("pinned_memories.json")
        self.ttl_seconds = ttl_seconds
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                self._data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        if self._pin_path.exists():
            try:
                self._pin_store = json.loads(self._pin_path.read_text(encoding="utf-8"))
            except Exception:
                self._pin_store = {}

    def _save(self) -> None:
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        with self._pin_path.open("w", encoding="utf-8") as f:
            json.dump(self._pin_store, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def store_interaction(
        self,
        prompt: str,
        answer: str,
        session_id: str,
        *,
        user_id: str | None = None,
        tags: List[str] | None = None,
    ) -> None:
        """Persist a prompt/answer pair for ``session_id``.

        ``tags`` may include "pin" to force-pin an interaction.
        """

        entry_hash = hashlib.sha256((prompt + answer).encode("utf-8")).hexdigest()
        now = time.time()

        with self._lock:
            is_pinned = "pin" in (tags or [])

            if is_pinned:
                bucket = self._pin_store.setdefault(session_id, [])
            else:
                bucket = self._data.setdefault(session_id, [])
                # exact hash-dedupe
                for item in bucket:
                    if item.get("hash") == entry_hash:
                        return
                # Jaro-Winkler dedupe vs last 3 answers
                for item in bucket[-3:]:
                    prev = item.get("answer", "")
                    if jaro_winkler_similarity(answer, prev) >= 0.9:
                        return

            bucket.append({
                "prompt": prompt,
                "answer": answer,
                "tags": tags or [],
                "timestamp": now,
                "hash": entry_hash,
            })

            self._save()


    def summarize_session(self, session_id: str, user_id: str | None = None) -> str:
        """Return a condensed representation of a session's interactions."""

        with self._lock:
            interactions = list(self._data.get(session_id, []))

        if not interactions:
            return ""

        parts: List[str] = []
        for item in interactions:
            p = shorten(item["prompt"].replace("\n", " "), width=60, placeholder="...")
            a = shorten(item["answer"].replace("\n", " "), width=60, placeholder="...")
            parts.append(f"{p} -> {a}")
        return " | ".join(parts)

    def retrieve_relevant_memories(self, prompt: str) -> List[Dict[str, Any]]:
        """Return stored interactions that appear related to ``prompt``.

        A very lightweight search is used: an interaction matches when the
        prompt substring is found in the original prompt or when any tag is
        mentioned in ``prompt``.
        """

        prompt_l = prompt.lower()
        results: List[Dict[str, Any]] = []
        with self._lock:
            stores = [self._data, self._pin_store]
            for store in stores:
                for interactions in store.values():
                    for item in interactions:
                        tags = [t.lower() for t in item.get("tags", [])]
                        if prompt_l in item["prompt"].lower() or any(t in prompt_l for t in tags):
                            results.append(item)
        return results

    # Pinned helpers ---------------------------------------------------
    def list_pins(self, session_id: str | None = None) -> List[Dict[str, Any]]:
        """Return pinned memories. If ``session_id`` is supplied, only that session."""

        with self._lock:
            if session_id is not None:
                return list(self._pin_store.get(session_id, []))
            all_items: List[Dict[str, Any]] = []
            for interactions in self._pin_store.values():
                all_items.extend(interactions)
            return all_items

    def retrieve_pinned_memories(self, prompt: str) -> List[Dict[str, Any]]:
        """Search only pinned memories for matches to ``prompt``."""

        prompt_l = prompt.lower()
        results: List[Dict[str, Any]] = []
        with self._lock:
            for interactions in self._pin_store.values():
                for item in interactions:
                    tags = [t.lower() for t in item.get("tags", [])]
                    if prompt_l in item["prompt"].lower() or any(t in prompt_l for t in tags):
                        results.append(item)
        return results

    def nightly_maintenance(self) -> None:
        """Deduplicate, purge stale entries and summarize old sessions."""

        now = time.time()
        with self._lock:
            for sid, interactions in list(self._data.items()):
                seen: set[str] = set()
                kept: List[Dict[str, Any]] = []
                for item in interactions:
                    if "pin" in item.get("tags", []):
                        kept.append(item)
                        continue
                    h = item.get("hash") or hashlib.sha256(
                        (item.get("prompt", "") + item.get("answer", "")).encode("utf-8")
                    ).hexdigest()
                    item["hash"] = h
                    if h in seen:
                        continue
                    seen.add(h)
                    ts = item.get("timestamp", now)
                    if now - ts > self.ttl_seconds:
                        continue
                    kept.append(item)

                if not kept:
                    summary = self.summarize_session(sid)
                    if summary:
                        kept.append(
                            {
                                "prompt": "summary",
                                "answer": summary,
                                "tags": ["summary"],
                                "timestamp": now,
                                "hash": hashlib.sha256(
                                    ("summary" + summary).encode("utf-8")
                                ).hexdigest(),
                            }
                        )

                self._data[sid] = kept

            self._save()


# Reusable singleton ---------------------------------------------------------
memgpt = MemGPT()

__all__ = ["MemGPT", "memgpt", "jaro_winkler_similarity"]
