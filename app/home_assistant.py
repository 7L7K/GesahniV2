import json as json_module
import logging
import os
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from . import alias_store
from . import analytics as _analytics
from .audit import append_audit  # Use the old audit.py directly
from .http_utils import json_request, log_exceptions
from .policy import moderation_precheck
from .telemetry import log_record_var

# ---------------------------------------------------------------------------
# Environment & Defaults
# ---------------------------------------------------------------------------
# Use localhost by default so the module can import even if the env var is
# missing. 8123 is the standard HA port.
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL", "http://localhost:8123")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    """Build request headers using the current token."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if HOME_ASSISTANT_TOKEN:
        headers["Authorization"] = f"Bearer {HOME_ASSISTANT_TOKEN}"
    return headers


# Room‑name synonyms so users can say “lounge” and we map → living room
ROOM_SYNONYMS = {
    "living room": ["lounge", "den", "livingroom"],
    "kitchen": ["cook room"],
    "bedroom": ["master", "primary"],
}
_SYN_TO_ROOM = {
    **{room: room for room in ROOM_SYNONYMS},
    **{syn: room for room, syns in ROOM_SYNONYMS.items() for syn in syns},
}

# Cache for /states results so resolve_entity doesn't spam the API.
_STATES_CACHE: list[dict] | None = None
_STATES_CACHE_EXP: float = 0.0
_STATES_TTL = 1.0  # seconds

# Service capabilities registry
_SERVICES_REGISTRY: dict[str, set[str]] = {}
_SERVICES_SCHEMA: dict[tuple[str, str], set[str]] = {}

# Risky actions that require explicit confirmation
_RISKY_ACTIONS: set[tuple[str, str]] = {
    ("lock", "unlock"),
    ("alarm_control_panel", "alarm_disarm"),
    ("cover", "open_cover"),
    ("cover", "close_cover"),
    ("climate", "turn_off"),
}


@dataclass(slots=True)
class CommandResult:
    success: bool
    message: str
    data: dict | None = None


class HomeAssistantAPIError(Exception):
    """Raised when a Home Assistant API call fails."""


def _redact(obj: Any) -> Any:
    """Recursively replace any access_token values with [redacted]."""
    if isinstance(obj, dict):
        return {
            k: ("[redacted]" if k == "access_token" else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


@log_exceptions("home_assistant")
async def _request(
    method: str, path: str, json: dict | None = None, timeout: float = 10.0
) -> Any:
    """Low‑level Home Assistant request helper with rich logging."""
    url = f"{HOME_ASSISTANT_URL.rstrip('/')}/api{path}"
    logger.info(
        "ha_request", extra={"meta": {"method": method, "path": path, "json": json}}
    )
    # Allow dry-run mode during fuzzing: skip network and return empty/no-op results
    if os.getenv("SKILLS_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        logger.debug("HA dry-run enabled; short-circuiting request %s %s", method, path)
        return {}  # best-effort empty response for dry-run

    data, error = await json_request(
        method,
        url,
        headers=_headers(),
        json=json,
        timeout=timeout,
    )

    body = json_module.dumps(_redact(data)) if not error else error
    if len(body) > 2048:
        body = body[:2048] + "..."
    logger.info(
        "ha_response",
        extra={"meta": {"status": 200 if not error else "err", "body": body}},
    )

    if error:
        try:
            # best-effort metric on HA failures
            await _analytics.record_ha_failure()
        except Exception:
            pass
        # Map low-level errors to a stable taxonomy for callers
        if error == "auth_error":
            raise HomeAssistantAPIError("unauthorized")
        if error == "not_found":
            raise HomeAssistantAPIError("not_found")
        if error in {"network_error", "unknown_error"}:
            raise HomeAssistantAPIError("timeout")
        raise HomeAssistantAPIError(error)
    return data


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------
async def get_states() -> list[dict]:
    """Return all HA entity states with a short lived cache."""
    global _STATES_CACHE, _STATES_CACHE_EXP
    now = time.monotonic()
    if _STATES_CACHE is not None and now < _STATES_CACHE_EXP:
        return _STATES_CACHE
    try:
        data = await _request("GET", "/states")
        _STATES_CACHE = data if isinstance(data, list) else []
        _STATES_CACHE_EXP = now + _STATES_TTL
    except Exception as e:
        logger.warning(
            "Failed to fetch states: %s (last cache exp: %.2f, now: %.2f)",
            e,
            _STATES_CACHE_EXP,
            now,
        )
        _STATES_CACHE = []
        _STATES_CACHE_EXP = 0.0
    return _STATES_CACHE


def invalidate_states_cache() -> None:
    """Clear cached HA states."""
    global _STATES_CACHE, _STATES_CACHE_EXP
    _STATES_CACHE = None
    _STATES_CACHE_EXP = 0.0


async def refresh_services_registry() -> None:
    """Fetch Home Assistant services and cache capabilities per domain/service.

    Populates:
      - _SERVICES_REGISTRY: {domain -> {service, ...}}
      - _SERVICES_SCHEMA: {(domain, service) -> {field, ...}}
    """
    global _SERVICES_REGISTRY, _SERVICES_SCHEMA
    try:
        data = await _request("GET", "/services")
        registry: dict[str, set[str]] = {}
        schema: dict[tuple[str, str], set[str]] = {}
        if isinstance(data, list):
            for dom in data:
                if not isinstance(dom, dict):
                    continue
                domain = dom.get("domain")
                if not isinstance(domain, str) or not domain:
                    continue
                services = dom.get("services", {}) or {}
                if not isinstance(services, dict):
                    continue
                registry.setdefault(domain, set())
                for svc_name, info in services.items():
                    if not isinstance(svc_name, str) or not svc_name:
                        continue
                    registry[domain].add(svc_name)
                    fields = set((info or {}).get("fields", {}).keys())
                    schema[(domain, svc_name)] = fields
        _SERVICES_REGISTRY = registry
        _SERVICES_SCHEMA = schema
        logger.info("HA services registry loaded: %d domains", len(_SERVICES_REGISTRY))
    except Exception as e:  # pragma: no cover - best effort
        logger.debug("Failed to refresh services registry: %s", e)


def is_service_available(domain: str, service: str) -> bool:
    services = _SERVICES_REGISTRY.get(domain)
    return bool(services and service in services)


def validate_service_call(domain: str, service: str, data: dict | None) -> None:
    """Best-effort validation against cached capabilities.

    When HA_STRICT_SERVICES=1 and a registry is loaded, raise on unknown services
    or unexpected payload keys. Otherwise, this is a no-op.
    """
    strict = os.getenv("HA_STRICT_SERVICES", "").lower() in {"1", "true", "yes"}
    if not strict:
        return
    if not _SERVICES_REGISTRY:
        return
    if not is_service_available(domain, service):
        raise HomeAssistantAPIError(f"Service not available: {domain}.{service}")
    allowed = _SERVICES_SCHEMA.get((domain, service))
    if allowed is not None and data:
        extra = set(data.keys()) - allowed
        # entity_id is commonly allowed implicitly by HA even if absent in schema
        extra.discard("entity_id")
        if extra:
            raise HomeAssistantAPIError(
                f"Unexpected fields for {domain}.{service}: {sorted(extra)}"
            )


def requires_confirmation(domain: str, service: str) -> bool:
    return (domain, service) in _RISKY_ACTIONS


async def call_service(domain: str, service: str, data: dict) -> Any:
    """Call an HA service and pipe basic telemetry into the log record var."""
    # Best-effort moderation pre-check for model-generated actions
    action_text = f"{domain}.{service} {data}"
    if not moderation_precheck(action_text):
        raise RuntimeError("action_blocked_by_policy")
    try:
        validate_service_call(domain, service, data)
    except Exception as e:
        logger.warning("HA service validation failed: %s", e)
        if os.getenv("HA_STRICT_SERVICES", "").lower() in {"1", "true", "yes"}:
            raise
    # Enforce confirmation for risky actions unless BYPASS_CONFIRM is enabled
    if os.getenv("BYPASS_CONFIRM", "").lower() not in {"1", "true", "yes"}:
        needs_confirm = False
        # Static allowlist
        if requires_confirmation(domain, service):
            needs_confirm = True
        # Dynamic: climate set_hvac_mode to off is risky
        try:
            if domain == "climate" and service == "set_hvac_mode":
                mode = str((data or {}).get("hvac_mode", "")).strip().lower()
                if mode == "off":
                    needs_confirm = True
        except Exception:
            pass
        # Dynamic: large group operations for lights/switches/fans
        try:
            if domain in {"light", "switch", "fan"} and service in {
                "turn_off",
                "turn_on",
            }:
                ids = (data or {}).get("entity_id")
                if isinstance(ids, list | tuple):
                    max_group = int(os.getenv("HA_CONFIRM_GROUP_SIZE", "5") or 5)
                    if len(ids) >= max_group:
                        needs_confirm = True
        except Exception:
            pass
        if needs_confirm:
            confirm = False
            for key in ("confirm", "__confirm__", "requires_confirm_ack"):
                if isinstance(data, dict) and data.get(key) in (
                    True,
                    1,
                    "1",
                    "true",
                    "yes",
                ):
                    confirm = True
                    break
            if not confirm:
                raise HomeAssistantAPIError("confirm_required")
    rec = log_record_var.get()
    if rec is not None:
        rec.ha_service_called = f"{domain}.{service}"
        ids = data.get("entity_id")
        if ids is not None:
            rec.entity_ids = [ids] if isinstance(ids, str) else list(ids)
    result = await _request("POST", f"/services/{domain}/{service}", json=data)
    invalidate_states_cache()
    try:
        rec = log_record_var.get()
        uid = getattr(rec, "user_id", None)
        append_audit(
            "ha_service",
            user_id_hashed=uid,
            data={"service": f"{domain}.{service}", "entity_id": data.get("entity_id")},
        )
    except Exception:
        pass
    return result


async def turn_on(entity_id: str) -> Any:
    domain = entity_id.split(".")[0]
    return await call_service(domain, "turn_on", {"entity_id": entity_id})


async def turn_off(entity_id: str) -> Any:
    domain = entity_id.split(".")[0]
    return await call_service(domain, "turn_off", {"entity_id": entity_id})


# ---------------------------------------------------------------------------
# Startup & Health Check
# ---------------------------------------------------------------------------
async def startup_check() -> None:
    """Verify HA connectivity, but never crash the whole app."""
    if not HOME_ASSISTANT_TOKEN:
        logger.warning("HA startup skipped – missing HOME_ASSISTANT_TOKEN env var")
        return

    try:
        await _request("GET", "/states")
        await refresh_services_registry()
        logger.info("Connected to Home Assistant successfully")
    except Exception as e:
        logger.warning("Home Assistant unreachable: %s", e)


# ---------------------------------------------------------------------------
# Prompt‑style command parser (very lightweight)
# ---------------------------------------------------------------------------
async def resolve_entity(name: str) -> list[str]:
    """Return entity IDs that match the given name, alias, or its synonyms.

    Resolution order:
    1) Exact alias match from alias_store (user-taught nicknames)
    2) Exact match on entity_id or friendly_name (case-insensitive)
    3) Synonym/room normalization then exact match
    4) Substring fallback on entity_id/friendly_name
    5) Domain plural to domain mapping (e.g. "lights" -> domain "light.*")
    """
    normalized = name.strip().lower()
    try:
        # During pytest runs, avoid disk alias lookups to keep tests deterministic
        if not os.getenv("PYTEST_CURRENT_TEST"):
            alias = await alias_store.get(normalized)
            if alias:
                return [alias]
    except Exception as e:
        logger.debug("alias lookup failed: %s", e)

    try:
        states = await get_states()
    except HomeAssistantAPIError as e:
        logger.warning("resolve_entity failed: %s", e)
        return []

    # 2) Exact entity_id or friendly_name match
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if normalized == eid.lower() or normalized == friendly.lower():
            return [eid]

    # 3) Synonym normalization then exact match
    target = _SYN_TO_ROOM.get(normalized, normalized)
    if target != normalized:
        for st in states:
            eid = st.get("entity_id", "")
            friendly = st.get("attributes", {}).get("friendly_name", "")
            if target == eid.lower() or target == friendly.lower():
                return [eid]

    # 4) Substring fallback
    matches: list[str] = []
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if target in eid.lower() or target in friendly.lower():
            matches.append(eid)

    # 5) Domain collection resolution (e.g., "lights" -> all light entities)
    if not matches:
        plural_to_domain = {
            "lights": "light",
            "switches": "switch",
            "fans": "fan",
            "covers": "cover",
            "scripts": "script",
            "scenes": "scene",
        }
        domain = plural_to_domain.get(target)
        if domain:
            matches = [
                st.get("entity_id", "")
                for st in states
                if st.get("entity_id", "").startswith(domain + ".")
            ]

    return [m for m in matches if m]


def _best_fuzzy_match(target: str, states: list[dict]) -> tuple[str | None, float]:
    """Return the best entity_id and confidence ratio [0,1] for a fuzzy match."""
    best_id: str | None = None
    best_score: float = 0.0
    t = target.strip().lower()
    for st in states:
        eid = st.get("entity_id", "")
        friendly = (st.get("attributes", {}) or {}).get("friendly_name", "")
        cand = friendly or eid
        score = SequenceMatcher(a=t, b=str(cand).lower()).ratio()
        if score > best_score:
            best_score, best_id = score, eid
    return best_id, best_score


_HANDLE_CMD_DEPRECATION_WARNED = False


async def handle_command(prompt: str) -> CommandResult | None:
    """[DEPRECATED] Parse HA control phrases and execute actions.

    This legacy path is superseded by the Skills system which should be used
    for all user intents. This function remains for backward compatibility but
    may be removed in a future version.

    Supports:
      - "turn on/off <name>"
      - "toggle <name>"
      - "set <name> brightness <0-100>" (lights)
    """
    global _HANDLE_CMD_DEPRECATION_WARNED
    if not _HANDLE_CMD_DEPRECATION_WARNED:
        logger.warning("home_assistant.handle_command is deprecated; use Skills instead")
        _HANDLE_CMD_DEPRECATION_WARNED = True
    text = prompt.strip()
    # toggle
    m = re.match(r"^(?:ha[:]?)?\s*toggle\s+(.+)$", text, re.I)
    if m:
        name = m.group(1).strip()
        entities = await resolve_entity(name)
        if not entities:
            # Try fuzzy
            states = await get_states()
            eid, score = _best_fuzzy_match(name, states)
            rec = log_record_var.get()
            if rec is not None:
                rec.match_confidence = float(score)
            if not eid:
                return CommandResult(False, "entity_not_found", {"name": name})
            if score < 0.8:
                return CommandResult(
                    False, "confirm_required", {"entities": [eid], "confidence": score}
                )
            entities = [eid]
        if len(entities) > 1:
            return CommandResult(False, "confirm_required", {"entities": entities})
        eid = entities[0]
        domain = eid.split(".")[0]
        try:
            await call_service(domain, "toggle", {"entity_id": eid})
            return CommandResult(True, f"Toggled {eid}")
        except Exception as e:
            logger.exception("Failed to toggle %s: %s", eid, e)
            return CommandResult(False, "command_failed")

    # set brightness
    m = re.match(
        r"^(?:ha[:]?)?\s*set\s+(.+?)\s+brightness\s+(\d{1,3})\s*%?$",
        text,
        re.I,
    )
    if m:
        name, bright_str = m.group(1).strip(), m.group(2)
        level = max(0, min(100, int(bright_str)))
        entities = await resolve_entity(name)
        if not entities:
            states = await get_states()
            eid, score = _best_fuzzy_match(name, states)
            rec = log_record_var.get()
            if rec is not None:
                rec.match_confidence = float(score)
            if not eid:
                return CommandResult(False, "entity_not_found", {"name": name})
            if score < 0.8:
                return CommandResult(
                    False, "confirm_required", {"entities": [eid], "confidence": score}
                )
            entities = [eid]
        if len(entities) > 1:
            return CommandResult(False, "confirm_required", {"entities": entities})
        eid = entities[0]
        try:
            await call_service(
                "light", "turn_on", {"entity_id": eid, "brightness_pct": level}
            )
            return CommandResult(True, f"Set {eid} brightness to {level}%")
        except Exception as e:
            logger.exception("Failed to set brightness for %s: %s", eid, e)
            return CommandResult(False, "command_failed")

    # turn on/off
    m = re.match(r"^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$", text, re.I)
    if not m:
        return None
    action, name = m.group(1).lower(), m.group(2).strip()
    entities = await resolve_entity(name)
    if not entities:
        states = await get_states()
        eid, score = _best_fuzzy_match(name, states)
        rec = log_record_var.get()
        if rec is not None:
            rec.match_confidence = float(score)
        if not eid:
            return CommandResult(False, "entity_not_found", {"name": name})
        if score < 0.8:
            return CommandResult(
                False, "confirm_required", {"entities": [eid], "confidence": score}
            )
        entities = [eid]
    if len(entities) > 1:
        return CommandResult(False, "confirm_required", {"entities": entities})

    entity_id = entities[0]
    try:
        if action == "on":
            await turn_on(entity_id)
            return CommandResult(True, f"Turned on {entity_id}")
        await turn_off(entity_id)
        return CommandResult(True, f"Turned off {entity_id}")
    except Exception as e:
        logger.exception("Failed to control %s: %s", entity_id, e)
        return CommandResult(False, "command_failed")
