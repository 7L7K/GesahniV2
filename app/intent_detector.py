"""Hybrid intent detector combining heuristics and a semantic classifier."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, Tuple

from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer, util

from .telemetry import log_record_var

# ---------------------------------------------------------------------------
# Heuristic matchers
# ---------------------------------------------------------------------------
GREETINGS: Iterable[str] = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "good morning",
    "good afternoon",
    "good evening",
}

# Match a wider set of control phrases such as "turn on", "switch off",
# "open the garage", etc.
CONTROL_RE = re.compile(
    r"\b(?:turn|switch|power|toggle|set)\s+(?:on|off|up|down)\b|"
    r"\b(?:open|close|lock|unlock)\b",
    re.IGNORECASE,
)

# Configurable threshold used for the semantic classifier
DEFAULT_THRESHOLD: float = float(os.getenv("INTENT_THRESHOLD", "0.7"))

# ---------------------------------------------------------------------------
# Semantic classifier (SBERT)
# ---------------------------------------------------------------------------
MODEL_NAME = os.getenv("SBERT_MODEL", "sentence-transformers/paraphrase-MiniLM-L3-v2")

EXAMPLE_INTENTS: Dict[str, list[str]] = {
    "chat": ["tell me a joke", "what's the weather like?"],
    "control": ["turn on the light", "switch off the fan"],
    "smalltalk": ["hello", "hi there"],
    "unknown": ["asdfgh", "lorem ipsum"],
}


@lru_cache(maxsize=1)
def _get_model() -> tuple[SentenceTransformer, Dict[str, Any]]:
    """Return the SBERT model and prototype embeddings."""
    model = SentenceTransformer(MODEL_NAME)
    embeds = {
        label: model.encode(texts, convert_to_tensor=True).mean(0)
        for label, texts in EXAMPLE_INTENTS.items()
    }
    return model, embeds


def _semantic_classify(text: str) -> Tuple[str, float]:
    """Return ``(intent, score)`` using cosine similarity over prototypes."""
    model, embeds = _get_model()
    emb = model.encode(text, convert_to_tensor=True)
    scores = {label: float(util.cos_sim(emb, proto)) for label, proto in embeds.items()}
    intent, score = max(scores.items(), key=lambda kv: kv[1])
    return intent, score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_intent(prompt: str, threshold: float = DEFAULT_THRESHOLD) -> tuple[str, str]:
    """Classify *prompt* returning ``(intent_category, confidence)``.

    Heuristics short‑circuit obvious greetings and control requests.  When these
    fail, a lightweight SBERT classifier assigns the prompt to the closest
    prototype intent.  ``threshold`` controls how confident the semantic match
    must be to be considered a real intent; below that it is marked ``unknown``.
    """

    prompt_l = prompt.lower().strip()

    # -- Greeting heuristic --------------------------------------------------
    if any(fuzz.partial_ratio(prompt_l, g) >= 80 for g in GREETINGS):
        score = 1.0
        intent, level = "smalltalk", "low"
        rec = log_record_var.get()
        if rec:
            rec.intent = intent
            rec.intent_confidence = score
        return intent, level

    # -- Control heuristic ---------------------------------------------------
    if CONTROL_RE.search(prompt_l):
        score = 1.0
        intent, level = "control", "high"
        rec = log_record_var.get()
        if rec:
            rec.intent = intent
            rec.intent_confidence = score
        return intent, level

    # Single-word prompts that aren't greetings are likely noise
    if len(prompt_l.split()) == 1:
        score = 0.0
        intent, level = "unknown", "low"
        rec = log_record_var.get()
        if rec:
            rec.intent = intent
            rec.intent_confidence = score
        return intent, level

    # -- Semantic fallback ---------------------------------------------------
    intent, score = _semantic_classify(prompt_l)
    if score < threshold:
        intent, level = "unknown", "low"
    else:
        level = "high" if score >= 0.9 else "medium"

    rec = log_record_var.get()
    if rec:
        rec.intent = intent
        rec.intent_confidence = float(score)
    return intent, level
