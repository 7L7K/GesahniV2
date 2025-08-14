### Home Assistant Integration

- **Endpoints**:
  - GET `/ha/entities`: dump states.
  - POST `/ha/service`: call arbitrary service with nonce gate; returns ok or error.
  - GET `/ha/resolve`: resolve friendly name to entity id.
  - POST `/ha/webhook`: signature‑verified webhook ack.
- **Signature verification**: HMAC SHA‑256 via `X-Signature` header; compares against `WEBHOOK_SECRET(S)`.
- **Scopes/nonce**: Service call requires `require_nonce` dependency; JWT scopes handled globally by security.
- **Service call flow**: Validate risky actions, optional strict schema validation from cached registry, moderation precheck, call HA REST, invalidate states cache, append audit, return result.
- **States/services**: `_request` is the low‑level fetcher; services registry populated from `/services`.

### Receipts

1) Entities endpoint
```45:51:app/api/ha.py
@router.get("/ha/entities")
return await get_states()
```

2) Service endpoint and nonce
```60:66:app/api/ha.py
@router.post("/ha/service")
req: ServiceRequest,
_nonce: None = Depends(require_nonce),
```

3) Webhook endpoint
```93:99:app/api/ha.py
@router.post("/ha/webhook")
_ = await verify_webhook(request)
return WebhookAck()
```

4) Resolve endpoint
```101:108:app/api/ha.py
@router.get("/ha/resolve")
entity = await resolve_entity(name)
```

5) Signature verification function
```927:943:app/security.py
async def verify_webhook(request: Request, x_signature: str | None = Header(...)):
... calc = sign_webhook(body, s)
if hmac.compare_digest(calc.lower(), sig):
    return body
raise HTTPException(status_code=401, detail="invalid_signature")
```

6) HA low‑level request helper
```92:101:app/home_assistant.py
@log_exceptions("home_assistant")
async def _request(method: str, path: str, json: dict | None = None, timeout: float = 10.0)
```

7) Call service flow and confirmation
```229:259:app/home_assistant.py
if not moderation_precheck(action_text): raise RuntimeError("action_blocked_by_policy")
validate_service_call(...)
if requires_confirmation(domain, service) and not BYPASS_CONFIRM: ... raise HomeAssistantAPIError("confirm_required")
result = await _request("POST", f"/services/{domain}/{service}", json=data)
invalidate_states_cache()
append_audit("ha_service", ...)
```

8) Risky actions and registry
```61:66:app/home_assistant.py
_RISKY_ACTIONS = { ("lock","unlock"), ("alarm_control_panel","alarm_disarm"), ("cover","open_cover") }
```
```166:192:app/home_assistant.py
await _request("GET", "/services")
_SERVICES_REGISTRY ... _SERVICES_SCHEMA ...
```

9) States cache and invalidation
```137:156:app/home_assistant.py
if _STATES_CACHE is not None and now < _STATES_CACHE_EXP: return _STATES_CACHE
... _STATES_CACHE = data ... _STATES_CACHE_EXP = now + _STATES_TTL
```
```159:164:app/home_assistant.py
def invalidate_states_cache() -> None: _STATES_CACHE = None; _STATES_CACHE_EXP = 0.0
```

10) Health endpoint for HA
```95:103:app/status.py
await _request("GET", "/states")
return {"status": "healthy", "latency_ms": latency}
```
