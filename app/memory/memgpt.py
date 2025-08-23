from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from textwrap import shorten
from threading import RLock
from typing import Any

try:  # optional, avoid import-time failures in tests
    from app.embeddings import embed_sync as _embed_sync
except Exception:  # pragma: no cover - allow running without embeddings backend
    _embed_sync = None  # type: ignore


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
        matches / s1_len + matches / s2_len + (matches - transpositions) / matches
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

    def __init__(
        self,
        storage_path: str | Path | None = None,
        ttl_seconds: int = 60 * 60 * 24 * 30,
    ) -> None:
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
        self._data: dict[str, list[dict[str, Any]]] = {}
        # Dedicated store for pinned memories
        self._pin_store: dict[str, list[dict[str, Any]]] = {}
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
    def write_claim(
        self,
        *,
        session_id: str,
        user_id: str | None,
        claim_text: str,
        evidence_links: list[str] | None,
        claim_type: str,
        entities: list[str] | list[dict[str, Any]] | None,
        confidence: float,
        horizon_days: float | None = None,
        pinned: bool = False,
    ) -> str | None:
        """Governed write of a claim with contract fields and hygiene.

        Returns claim checksum on success, None when gated or deduped away.
        """

        now = time.time()
        links = [l for l in (evidence_links or []) if isinstance(l, str) and l.strip()]

        redacted_text, redactions = self._redact_pii(claim_text)
        checksum = hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()
        simhash = self._simhash(redacted_text)
        norm_entities = self._normalize_entities(entities)
        importance = self._importance_score(redacted_text, norm_entities, links)
        novelty = self._novelty_score(redacted_text, user_id)

        thr_novelty = float(os.getenv("MEMGPT_NOVELTY_THRESHOLD", "0.25"))
        thr_importance = float(os.getenv("MEMGPT_IMPORTANCE_THRESHOLD", "0.50"))
        if not pinned and not (novelty >= thr_novelty and importance >= thr_importance):
            return None

        if self._is_duplicate(checksum=checksum, simhash=simhash, text=redacted_text, user_id=user_id):
            return None

        horizon = float(horizon_days) if horizon_days is not None else self._default_horizon_days(claim_type)
        decay_at = now + max(1.0, horizon * 24.0 * 3600.0)

        record = {
            "kind": "claim",
            "user_id": user_id,
            "session_id": session_id,
            "text": redacted_text,
            "evidence": links,
            "type": claim_type,
            "entities": norm_entities,
            "confidence": float(max(0.0, min(1.0, confidence))),
            "horizon_days": float(horizon),
            "decay_at": float(decay_at),
            "checksum": checksum,
            "simhash": simhash,
            # store mapping out-of-band; keep empty object for schema stability
            "redactions": {},
            "quality": 1.0,
            "importance": float(importance),
            "novelty": float(novelty),
            "pinned": bool(pinned),
            "timestamp": now,
        }

        # Persist redaction map separately so the main store has no raw PII
        try:
            from app.redaction import store_redaction_map
            store_redaction_map("memgpt_claim", checksum, redactions)
        except Exception:
            pass
        # Audit when content is pinned
        try:
            if pinned:
                from app.telemetry import hash_user_id

                from ..audit import append_audit
                append_audit(
                    "pin_claim",
                    user_id_hashed=hash_user_id(user_id or ""),
                    data={"session_id": session_id, "checksum": checksum, "type": claim_type},
                )
        except Exception:
            pass

        with self._lock:
            bucket = self._pin_store.setdefault(session_id, []) if pinned else self._data.setdefault(session_id, [])
            bucket.append(record)
            self._save()
        return checksum
    def store_interaction(
        self,
        prompt: str,
        answer: str,
        session_id: str,
        *,
        user_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Persist a prompt/answer pair for ``session_id``.

        ``tags`` may include "pin" to force-pin an interaction.
        """

        entry_hash = hashlib.sha256((prompt + answer).encode("utf-8")).hexdigest()
        now = time.time()

        # Redact prompt/answer before storage and persist mapping out-of-band
        try:
            from app.redaction import redact_pii, store_redaction_map
            rp, mp = redact_pii(prompt)
            ra, ma = redact_pii(answer)
            prompt, answer = rp, ra
            merged = {}
            merged.update(mp)
            merged.update(ma)
            store_redaction_map("memgpt_interaction", entry_hash, merged)
        except Exception:
            pass

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

            bucket.append(
                {
                    "prompt": prompt,
                    "answer": answer,
                    "tags": tags or [],
                    "timestamp": now,
                    "hash": entry_hash,
                }
            )

            self._save()

        # Audit pin
        try:
            if is_pinned:
                from app.telemetry import hash_user_id

                from ..audit import append_audit
                append_audit(
                    "pin_interaction",
                    user_id_hashed=hash_user_id(user_id or ""),
                    data={"session_id": session_id, "hash": entry_hash},
                )
        except Exception:
            pass

    def summarize_session(self, session_id: str, user_id: str | None = None) -> str:
        """Return a condensed representation of a session's interactions."""

        with self._lock:
            interactions = list(self._data.get(session_id, []))

        if not interactions:
            return ""

        parts: list[str] = []
        for item in interactions:
            p = shorten(item["prompt"].replace("\n", " "), width=60, placeholder="...")
            a = shorten(item["answer"].replace("\n", " "), width=60, placeholder="...")
            parts.append(f"{p} -> {a}")
        return " | ".join(parts)

    def retrieve_relevant_memories(self, prompt: str) -> list[dict[str, Any]]:
        """Return stored interactions that appear related to ``prompt``.

        A very lightweight search is used: an interaction matches when the
        prompt substring is found in the original prompt or when any tag is
        mentioned in ``prompt``.
        """

        prompt_l = prompt.lower()
        results: list[dict[str, Any]] = []
        with self._lock:
            stores = [self._data, self._pin_store]
            for store in stores:
                for interactions in store.values():
                    for item in interactions:
                        tags = [t.lower() for t in item.get("tags", [])]
                        if prompt_l in item["prompt"].lower() or any(
                            t in prompt_l for t in tags
                        ):
                            results.append(item)
        return results

    # Pinned helpers ---------------------------------------------------
    def list_pins(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """Return pinned memories. If ``session_id`` is supplied, only that session."""

        with self._lock:
            if session_id is not None:
                return list(self._pin_store.get(session_id, []))
            all_items: list[dict[str, Any]] = []
            for interactions in self._pin_store.values():
                all_items.extend(interactions)
            return all_items

    def retrieve_pinned_memories(self, prompt: str) -> list[dict[str, Any]]:
        """Search only pinned memories for matches to ``prompt``."""

        prompt_l = prompt.lower()
        results: list[dict[str, Any]] = []
        with self._lock:
            for interactions in self._pin_store.values():
                for item in interactions:
                    tags = [t.lower() for t in item.get("tags", [])]
                    if prompt_l in item["prompt"].lower() or any(
                        t in prompt_l for t in tags
                    ):
                        results.append(item)
        return results

    def nightly_maintenance(self) -> None:
        """Deduplicate, apply decay/rollups to claims, purge stale entries, summarize old sessions."""

        now = time.time()
        with self._lock:
            for sid, interactions in list(self._data.items()):
                seen: set[str] = set()
                kept: list[dict[str, Any]] = []
                claims_buffer: list[dict[str, Any]] = []
                for item in interactions:
                    if "pin" in item.get("tags", []):
                        kept.append(item)
                        continue
                    if item.get("kind") == "claim":
                        claims_buffer.append(item)
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

                # Apply decay and rollups on claims
                decayed, rollups, tombstoned = self._decay_and_rollup_claims(claims_buffer, now)
                kept.extend(decayed)
                kept.extend(rollups)

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

    # ----------------------- Governance helpers ------------------------
    def _normalize_entities(self, entities: list[str] | list[dict[str, Any]] | None) -> list[str]:
        out: list[str] = []
        for e in entities or []:
            if isinstance(e, str):
                name = e.strip()
            elif isinstance(e, dict):
                name = str(e.get("name") or e.get("id") or "").strip()
            else:
                name = ""
            if name:
                out.append(name)
        return out[:10]

    def _default_horizon_days(self, claim_type: str) -> float:
        table = {
            "event": float(os.getenv("MEMGPT_HORIZON_EVENT_DAYS", "30")),
            "fact": float(os.getenv("MEMGPT_HORIZON_FACT_DAYS", "365")),
            "preference": float(os.getenv("MEMGPT_HORIZON_PREF_DAYS", "180")),
        }
        return float(table.get(claim_type.lower(), float(os.getenv("MEMGPT_HORIZON_DEFAULT_DAYS", "90"))))

    def _redact_pii(self, text: str) -> tuple[str, dict[str, str]]:
        redactions: dict[str, str] = {}
        counter = {"EMAIL": 0, "PHONE": 0, "SSN": 0}

        def repl(kind: str, value: str) -> str:
            counter[kind] += 1
            key = f"[PII_{kind}_{counter[kind]}]"
            redactions[key] = value
            return key

        # crude patterns; reversible via mapping
        email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        phone_re = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}\b")
        ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

        t = email_re.sub(lambda m: repl("EMAIL", m.group(0)), text)
        t = phone_re.sub(lambda m: repl("PHONE", m.group(0)), t)
        t = ssn_re.sub(lambda m: repl("SSN", m.group(0)), t)
        return t, redactions

    def _simhash(self, text: str, bits: int = 64) -> int:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        vec = [0] * bits
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            for i in range(bits):
                bit = 1 if (h >> i) & 1 else -1
                vec[i] += bit
        out = 0
        for i, v in enumerate(vec):
            if v > 0:
                out |= (1 << i)
        return out

    def _hamming(self, a: int, b: int) -> int:
        x = a ^ b
        cnt = 0
        while x:
            x &= x - 1
            cnt += 1
        return cnt

    def _cosine_sim(self, a: str, b: str) -> float:
        if _embed_sync is None:
            return jaro_winkler_similarity(a, b)
        va = _embed_sync(a)
        vb = _embed_sync(b)
        num = sum(x * y for x, y in zip(va, vb, strict=False))
        na = (sum(x * x for x in va) ** 0.5) or 1.0
        nb = (sum(y * y for y in vb) ** 0.5) or 1.0
        return float(num / (na * nb))

    def _novelty_score(self, text: str, user_id: str | None) -> float:
        corpus: list[str] = []
        for store in (self._data, self._pin_store):
            for interactions in store.values():
                for item in interactions:
                    if item.get("kind") == "claim" and (user_id is None or item.get("user_id") == user_id):
                        corpus.append(item.get("text", ""))
        if not corpus:
            return 1.0
        max_sim = 0.0
        for t in corpus[-100:]:
            max_sim = max(max_sim, self._cosine_sim(text, t))
        return float(max(0.0, 1.0 - max_sim))

    def _importance_score(self, text: str, entities: list[str], links: list[str]) -> float:
        score = 0.0
        score += 0.2 if len(text) >= 40 else 0.0
        score += min(0.4, 0.1 * len(entities))
        score += min(0.4, 0.2 * len(links))
        if any(k in text.lower() for k in ("deadline", "due", "meeting", "invoice", "api", "error")):
            score += 0.2
        return float(min(1.0, score))

    def _is_duplicate(self, *, checksum: str, simhash: int, text: str, user_id: str | None) -> bool:
        max_hamming = int(os.getenv("MEMGPT_SIMHASH_HAMMING_MAX", "3"))
        max_cosine = float(os.getenv("MEMGPT_COSINE_DUP_MAX", "0.90"))
        for store in (self._data, self._pin_store):
            for interactions in store.values():
                for item in interactions:
                    if item.get("kind") != "claim":
                        continue
                    if user_id is not None and item.get("user_id") != user_id:
                        continue
                    if item.get("checksum") == checksum:
                        return True
                    try:
                        sh = int(item.get("simhash"))
                        if self._hamming(simhash, sh) <= max_hamming:
                            return True
                    except Exception:
                        pass
                    t = item.get("text", "")
                    if t and self._cosine_sim(text, t) >= max_cosine:
                        return True
        return False

    def _decay_and_rollup_claims(self, claims: list[dict[str, Any]], now: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        decayed: list[dict[str, Any]] = []
        rollups: list[dict[str, Any]] = []
        tombstoned_ids: list[str] = []

        decay_factor = float(os.getenv("MEMGPT_DECAY_FACTOR", "0.7"))
        rollup_min_cluster = int(os.getenv("MEMGPT_ROLLUP_MIN_CLUSTER", "3"))
        rollup_importance_max = float(os.getenv("MEMGPT_ROLLUP_IMPORTANCE_MAX", "0.3"))
        rollup_window_days = float(os.getenv("MEMGPT_ROLLUP_WINDOW_DAYS", "30"))
        window_sec = rollup_window_days * 24.0 * 3600.0

        active: list[dict[str, Any]] = []
        for c in claims:
            if c.get("tombstoned"):
                continue
            ts = float(c.get("timestamp", now))
            if now - ts > self.ttl_seconds and not c.get("pinned", False):
                continue
            da = float(c.get("decay_at", 0) or 0.0)
            if da and now >= da and not c.get("pinned", False):
                q = float(c.get("quality", 1.0)) * decay_factor
                c["quality"] = max(0.0, q)
            active.append(c)
        decayed.extend(active)

        # Rollup low-importance crumbs within window by entity/topic
        crumbs = [c for c in active if float(c.get("importance", 0.0)) <= rollup_importance_max and (now - float(c.get("timestamp", now)) <= window_sec) and not c.get("pinned", False)]
        clusters: dict[str, list[dict[str, Any]]] = {}
        for c in crumbs:
            ents = c.get("entities") or []
            topic = (ents[0] if isinstance(ents, list) and ents else (c.get("type") or "misc")).lower()
            clusters.setdefault(topic, []).append(c)

        for topic, items in list(clusters.items()):
            if len(items) < rollup_min_cluster:
                continue
            summary = self._summarize_cluster(items, topic)
            backrefs = [ci.get("checksum") for ci in items if ci.get("checksum")]
            checksum = hashlib.sha256((summary + topic).encode("utf-8")).hexdigest()
            rollup_record = {
                "kind": "claim",
                "user_id": items[0].get("user_id"),
                "session_id": items[0].get("session_id"),
                "text": summary,
                "evidence": [],
                "type": f"rollup:{topic}",
                "entities": list({topic}),
                "confidence": 0.6,
                "horizon_days": self._default_horizon_days("fact"),
                "decay_at": now + self._default_horizon_days("fact") * 24 * 3600,
                "checksum": checksum,
                "simhash": self._simhash(summary),
                "redactions": {},
                "quality": 1.0,
                "importance": 0.5,
                "novelty": 1.0,
                "pinned": False,
                "timestamp": now,
                "backrefs": backrefs,
            }
            rollups.append(rollup_record)
            for it in items:
                it["tombstoned"] = True
                tombstoned_ids.append(str(it.get("checksum")))

        # Keep non-tombstoned claims
        decayed = [c for c in decayed if not c.get("tombstoned")]
        return decayed, rollups, tombstoned_ids

    def _summarize_cluster(self, items: list[dict[str, Any]], topic: str) -> str:
        parts: list[str] = []
        for it in items[:5]:
            txt = it.get("text", "").strip().replace("\n", " ")
            parts.append(shorten(txt, width=120, placeholder="..."))
        uniq = []
        for p in parts:
            if p not in uniq:
                uniq.append(p)
        return f"Summary about {topic}: " + " | ".join(uniq)

    # ------------------------------------------------------------------
    # Admin helpers
    # ------------------------------------------------------------------
    def delete_by_hash(self, hash_value: str) -> bool:
        """Delete a memory (pinned or episodic) by its stored hash.

        Returns True when something was removed.
        """

        removed = False
        with self._lock:
            for store in (self._data, self._pin_store):
                for sid, interactions in list(store.items()):
                    kept: list[dict[str, Any]] = []
                    for item in interactions:
                        if str(item.get("hash")) == str(hash_value):
                            removed = True
                            continue
                        kept.append(item)
                    store[sid] = kept
        if removed:
            self._save()
        return removed


# Reusable singleton ---------------------------------------------------------
memgpt = MemGPT()

__all__ = ["MemGPT", "memgpt", "jaro_winkler_similarity"]
