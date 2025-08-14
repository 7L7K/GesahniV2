from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Literal, Optional, Tuple
import hashlib

from .telemetry import log_record_var
from .metrics import TTS_FALLBACKS, TTS_COST_USD, TTS_LATENCY_SECONDS, TTS_REQUEST_COUNT
from .intent_detector import detect_intent
from .history import append_history
from .policy import moderation_precheck

from .adapters.voice.piper_tts import synthesize_piper
from .adapters.voice.openai_tts import synthesize_openai_tts


Mode = Literal["utility", "capture"]
Tier = Literal["piper", "mini_tts", "tts1", "tts1_hd"]


@dataclass
class TTSConfig:
    default_capture_tier: Tier = "mini_tts"
    default_utility_tier: Tier = "piper"
    monthly_cap_usd: float = 15.0
    voice_mode: Literal["auto", "always_openai", "always_piper"] = "auto"
    privacy_local_only: bool = True


def _load_config() -> TTSConfig:
    return TTSConfig(
        default_capture_tier=os.getenv("DEFAULT_CAPTURE_TIER", "mini_tts") or "mini_tts",
        default_utility_tier=os.getenv("DEFAULT_UTILITY_TIER", "piper") or "piper",
        monthly_cap_usd=float(os.getenv("MONTHLY_TTS_CAP", "15") or 15),
        voice_mode=(os.getenv("VOICE_MODE", "auto").strip().lower() or "auto"),
        privacy_local_only=(os.getenv("TTS_PRIVACY_LOCAL_ONLY", "1").strip().lower() in {"1", "true", "yes"}),
    )


class TTSSpend:
    _month_epoch: float | None = None
    _spent_usd: float = 0.0
    _day_epoch: float | None = None
    _spent_day_usd: float = 0.0

    @classmethod
    def _month(cls) -> float:
        return time.time() // (86400 * 30)

    @classmethod
    def _roll(cls) -> None:
        cur_m = cls._month()
        if cls._month_epoch != cur_m:
            cls._month_epoch = cur_m
            cls._spent_usd = 0.0
        # Daily epoch (UTC day)
        cur_d = time.time() // 86400
        if cls._day_epoch != cur_d:
            cls._day_epoch = cur_d
            cls._spent_day_usd = 0.0

    @classmethod
    def add(cls, usd: float) -> float:
        cls._roll()
        cls._spent_usd += max(0.0, float(usd))
        return cls._spent_usd

    @classmethod
    def total(cls) -> float:
        cls._roll()
        return cls._spent_usd

    @classmethod
    def add_day(cls, usd: float) -> float:
        cls._roll()
        cls._spent_day_usd += max(0.0, float(usd))
        return cls._spent_day_usd

    @classmethod
    def total_day(cls) -> float:
        cls._roll()
        return cls._spent_day_usd

    @classmethod
    def snapshot(cls) -> dict:
        cls._roll()
        cfg = _load_config()
        spent = float(cls._spent_usd)
        cap = float(cfg.monthly_cap_usd)
        ratio = spent / cap if cap > 0 else 0.0
        # Daily view (auto-degrade threshold controlled by env)
        day_cap = float(os.getenv("DAILY_TTS_CAP_USD", os.getenv("DAILY_TTS_BUDGET_USD", "3.0")) or 3.0)
        warn_ratio = float(os.getenv("DAILY_TTS_WARN_RATIO", "0.8") or 0.8)
        day_spent = float(cls._spent_day_usd)
        day_ratio = day_spent / day_cap if day_cap > 0 else 0.0
        return {
            "spent_usd": round(spent, 6),
            "cap_usd": cap,
            "ratio": ratio,
            "near_cap": ratio >= 0.8 and ratio < 1.0,
            "blocked": ratio >= 1.0,
            # Daily fields
            "day_spent_usd": round(day_spent, 6),
            "day_cap_usd": day_cap,
            "day_ratio": day_ratio,
            "day_near_cap": day_ratio >= warn_ratio and day_ratio < 1.0,
            "day_blocked": day_ratio >= 1.0,
        }


def _is_sensitive(text: str) -> bool:
    # Lightweight PII heuristic: rely on history scrubber patterns and moderation
    # Here we only guard obvious cases; a full PII detector would be heavier.
    if not text:
        return False
    import re

    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phone = re.search(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)?\d{3}[\s-]?\d{4}(?!\d)", text)
    ssn = re.search(r"\b\d{3}-\d{2}-\d{4}\b", text)
    return bool(email or phone or ssn)


def _pick_engine(mode: Mode, intent: str, cfg: TTSConfig) -> Tuple[str, Tier]:
    # User override first
    if cfg.voice_mode == "always_piper":
        return "piper", "piper"
    if cfg.voice_mode == "always_openai":
        tier = cfg.default_capture_tier if mode == "capture" else cfg.default_utility_tier
        return "openai", tier if tier != "piper" else "mini_tts"

    # Intent-driven
    if intent in {"story", "narrative", "meditation", "longform", "recall_story"}:
        return "openai", cfg.default_capture_tier
    # Utility: status/notification/control
    if intent in {"control", "smalltalk", "search", "chat"}:
        return "piper", "piper"
    # Fallback to mode
    return ("openai", cfg.default_capture_tier) if mode == "capture" else ("piper", "piper")


async def synthesize(
    *,
    text: str,
    mode: Mode = "utility",
    intent_hint: Optional[str] = None,
    sensitivity_hint: Optional[bool] = None,
    openai_voice: Optional[str] = None,
) -> bytes:
    """Central orchestrator: picks engine, enforces budget, fallbacks, logs metrics.

    Fallbacks: retry once on same engine, then flip to other engine with a short notice prefix.
    """

    cfg = _load_config()
    # privacy: sensitive -> force Piper when enabled
    sensitive = bool(sensitivity_hint) or _is_sensitive(text)
    if cfg.privacy_local_only and sensitive:
        engine, tier = "piper", "piper"
    else:
        # infer intent if not provided
        intent = intent_hint or detect_intent(text)[0]
        engine, tier = _pick_engine(mode, intent, cfg)

    # budget guard (monthly + daily auto-degrade)
    spent_m = TTSSpend.total()
    if spent_m >= cfg.monthly_cap_usd and cfg.voice_mode != "always_openai":
        engine, tier = "piper", "piper"
    # Daily guard: flip to Piper when over warn ratio/cap
    daily_cap = float(os.getenv("DAILY_TTS_CAP_USD", os.getenv("DAILY_TTS_BUDGET_USD", "3.0")) or 3.0)
    warn_ratio = float(os.getenv("DAILY_TTS_WARN_RATIO", "0.8") or 0.8)
    spent_d = TTSSpend.total_day()
    if daily_cap > 0 and (spent_d / daily_cap) >= warn_ratio and engine != "piper":
        engine, tier = "piper", "piper"

    rec = log_record_var.get()
    if rec:
        rec.engine_used = f"tts:{engine}:{tier}"

    # In-memory TTL cache to avoid repeated synthesis cost for identical requests
    _ttl_s = int(os.getenv("TTS_CACHE_TTL_S", "600") or 600)
    key_voice = (openai_voice or "piper") if engine == "openai" else "piper"
    _key = f"{engine}:{tier}:{key_voice}:{hashlib.sha1((text or '').encode('utf-8')).hexdigest()}"
    # simple module-level cache
    global _TTS_CACHE  # type: ignore[var-annotated]
    try:
        _TTS_CACHE
    except NameError:
        _TTS_CACHE = {}  # type: ignore[assignment]

    now = time.time()
    try:
        exp, cached = _TTS_CACHE.get(_key, (0.0, b""))  # type: ignore[attr-defined]
        if exp and now < float(exp) and isinstance(cached, (bytes, bytearray)) and cached:
            return bytes(cached)
    except Exception:
        pass

    async def _call() -> Tuple[bytes, float]:
        if engine == "piper":
            return await synthesize_piper(text=text)
        audio, cost, _ = await synthesize_openai_tts(text=text, tier=tier, voice=openai_voice)
        return audio, cost

    # Try primary
    for attempt in (1, 2):
        try:
            start = time.perf_counter()
            audio, cost = await _call()
            if cost:
                new_total = TTSSpend.add(cost)
                TTSSpend.add_day(cost)
                TTS_COST_USD.labels(engine, tier if engine == "openai" else "piper").observe(cost)
                # hard block above cap unless always_openai is forced
                if new_total > cfg.monthly_cap_usd and cfg.voice_mode != "always_openai":
                    # Return a brief local notice instead
                    engine, tier = "piper", "piper"
                    TTS_FALLBACKS.labels("openai", "piper", "budget_cap").inc()
                    notice = "Switching voice due to budget cap. "
                    loc_audio, _ = await synthesize_piper(text=notice)
                    return loc_audio
            TTS_LATENCY_SECONDS.labels(engine, tier if engine == "openai" else "piper").observe(
                time.perf_counter() - start
            )
            # store in cache
            try:
                _TTS_CACHE[_key] = (now + float(_ttl_s), bytes(audio))  # type: ignore[index]
            except Exception:
                pass
            return audio
        except Exception as e:
            if attempt == 1:
                await asyncio.sleep(0.05)
                continue
            # swap engine
            prev = engine
            engine = "piper" if prev == "openai" else "openai"
            tier = "piper" if engine == "piper" else (cfg.default_capture_tier if mode == "capture" else cfg.default_utility_tier)
            TTS_FALLBACKS.labels(prev, engine, "error").inc()
            notice = "Switching voice due to network/quota. "
            try:
                if engine == "piper":
                    audio2, _ = await synthesize_piper(text=notice + text)
                else:
                    audio2, cost2 = (await synthesize_openai_tts(text=notice + text, tier=tier))[:2]
                    if cost2:
                        TTSSpend.add(cost2)
                return audio2
            except Exception:
                # give up silently
                return b""



