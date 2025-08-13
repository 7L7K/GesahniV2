"""Hybrid intent detector combining heuristics and a semantic classifier."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, Tuple, Literal, TYPE_CHECKING

from rapidfuzz import fuzz

# NOTE: Avoid importing sentence-transformers at module import time to prevent
# fork warnings with uvicorn --reload and to keep startup fast. We import
# lazily inside helpers.
if TYPE_CHECKING:  # pragma: no cover - for static type checkers only
    from sentence_transformers import SentenceTransformer  # noqa: F401

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
    "chat": [
        "tell me a joke",
        "what's the weather like?",
        "tell me a fun fact",
        "say something interesting",
        "share a riddle",
        "got any trivia?",
        "do you know a random fact?",
        "make me laugh",
        "what's something cool?",
        "can you amuse me?",
    ],
    "control": ["turn on the light", "switch off the fan"],
    # recall_story maps queries to search past transcripts/memories
    "recall_story": [
        "what did grandma say", 
        "recall the story about", 
        "remind me what we discussed", 
        "what did i say yesterday",
        "what did we talk about last time",
    ],
    "smalltalk": ["hello", "hi there"],
    "unknown": ["asdfgh", "lorem ipsum"],
}


@lru_cache(maxsize=1)
def _get_model() -> tuple["SentenceTransformer", Dict[str, Any]]:
    """Return the SBERT model and prototype embeddings."""
    try:
        from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore
    except Exception:
        raise RuntimeError("sentence-transformers not installed")

    model = _SentenceTransformer(MODEL_NAME)
    embeds = {
        # Suppress progress bar to avoid noisy 'Batches: 100%' logs
        label: model.encode(texts, convert_to_tensor=True, show_progress_bar=False).mean(0)
        for label, texts in EXAMPLE_INTENTS.items()
    }
    return model, embeds


def _semantic_classify(text: str) -> Tuple[str, float, bool]:
    """Return ``(intent, score, exact)`` using a semantic model or fuzzy matching."""
    try:
        from sentence_transformers import util as _util  # type: ignore
        model, embeds = _get_model()
    except Exception:
        # Fallback: no sentence-transformers available
        best_label = "unknown"
        best_score = 0.0
        exact = False
        for label, examples in EXAMPLE_INTENTS.items():
            for ex in examples:
                score = fuzz.partial_ratio(text, ex)
                if score > best_score:
                    best_label, best_score = label, float(score)
                    exact = text == ex
        return best_label, best_score / 100.0, exact
    emb = model.encode(text, convert_to_tensor=True, show_progress_bar=False)
    scores = {label: float(_util.cos_sim(emb, proto)) for label, proto in embeds.items()}
    intent, score = max(scores.items(), key=lambda kv: kv[1])
    return intent, score, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


Priority = Literal["low", "medium", "high"]


def detect_intent(
    prompt: str, threshold: float = DEFAULT_THRESHOLD
) -> tuple[str, Priority]:
    """Classify *prompt* returning ``(intent_category, priority)``.

    ``priority`` is derived from the underlying confidence score and is one of
    ``"low"``, ``"medium"``, or ``"high"``. Heuristics short‑circuit obvious
    greetings and control requests. When those fail, a lightweight SBERT
    classifier assigns the prompt to the closest prototype intent. ``threshold``
    controls how confident the semantic match must be to be considered a real
    intent; below that it is marked ``unknown``.
    """

    prompt_l = prompt.lower().strip()

    # -- Greeting heuristic --------------------------------------------------
    if any(fuzz.partial_ratio(prompt_l, g) >= 80 for g in GREETINGS):
        score = 1.0
        intent, priority = "smalltalk", "low"
        rec = log_record_var.get()
        if rec:
            rec.intent = intent
            rec.intent_confidence = score
        return intent, priority

    # -- Control heuristic ---------------------------------------------------
    if CONTROL_RE.search(prompt_l):
        score = 1.0
        intent, priority = "control", "high"
        rec = log_record_var.get()
        if rec:
            rec.intent = intent
            rec.intent_confidence = score
        return intent, priority

    # Recall heuristic: simple phrase triggers for story recall
    if any(k in prompt_l for k in ("what did i say", "what did we talk", "recall", "remember")):
        rec = log_record_var.get()
        if rec:
            rec.intent = "recall_story"
            rec.intent_confidence = 0.9
        return "recall_story", "medium"

    # Single-word prompts that aren't greetings are likely noise
    if len(prompt_l.split()) == 1:
        score = 0.0
        intent, priority = "unknown", "low"
        rec = log_record_var.get()
        if rec:
            rec.intent = intent
            rec.intent_confidence = score
        return intent, priority

    # -- Semantic fallback ---------------------------------------------------
    intent, score, exact = _semantic_classify(prompt_l)
    if score < threshold:
        intent, priority = "unknown", "low"
    else:
        if score > 0.9:
            priority = "medium" if exact else "high"
        elif score >= 0.75:
            priority = "medium"
        else:
            priority = "low"

    rec = log_record_var.get()
    if rec:
        rec.intent = intent
        rec.intent_confidence = float(score)
    return intent, priority
