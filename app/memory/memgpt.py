from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from textwrap import shorten
from typing import Any, Dict, List


class MemGPT:
    """Simple in-process memory manager.

    The class stores prompt/answer pairs per session in a JSON file and can
    return condensed session summaries or interactions that match a prompt.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path or Path(__file__).resolve().parent.parent / "data" / "memories.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._data: Dict[str, List[Dict[str, Any]]] = {}
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

    def _save(self) -> None:
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def store_interaction(self, prompt: str, answer: str, session_id: str, tags: List[str] | None = None) -> None:
        """Persist a prompt/answer pair for ``session_id``.

        ``tags`` may be supplied to aid later retrieval.
        """

        with self._lock:
            bucket = self._data.setdefault(session_id, [])
            bucket.append({"prompt": prompt, "answer": answer, "tags": tags or []})
            self._save()

    def summarize_session(self, session_id: str) -> str:
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
            for interactions in self._data.values():
                for item in interactions:
                    tags = [t.lower() for t in item.get("tags", [])]
                    if prompt_l in item["prompt"].lower() or any(t in prompt_l for t in tags):
                        results.append(item)
        return results


# Reusable singleton ---------------------------------------------------------
memgpt = MemGPT()

__all__ = ["MemGPT", "memgpt"]
