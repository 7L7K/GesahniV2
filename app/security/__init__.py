# Security module package

from .jwt_config import JWTConfig, get_jwt_config
from .webhooks import rotate_webhook_secret, sign_webhook, verify_webhook

# Import jwt_decode from the main security module (app.security)
try:
    from .security import (
        _apply_rate_limit,
        _get_request_payload,
        _http_requests,
        _payload_scopes,
        decode_jwt,
        get_rate_limit_snapshot,
        http_burst,
        jwt_decode,
        rate_limit,
        rate_limit_problem,
        rate_limit_with,
        require_nonce,
        scope_rate_limit,
        validate_websocket_origin,
        verify_token,
        verify_token_strict,
        verify_ws,
    )
except ImportError:
    # Fallback for circular import situations: provide minimal implementations
    from typing import Any as _Any

    import jwt as _pyjwt  # type: ignore

    def jwt_decode(token: str, key: str | bytes | None = None, algorithms: list[str] | None = None, **kwargs: _Any) -> dict:
        algs = algorithms or ["HS256"]
        return _pyjwt.decode(token, key, algorithms=algs, **kwargs)  # type: ignore[arg-type]

    def decode_jwt(token: str) -> dict | None:
        try:
            from .jwt_config import get_jwt_config as _get
            cfg = _get()
            if cfg.alg == "HS256":
                return _pyjwt.decode(token, cfg.secret, algorithms=["HS256"], options={"verify_aud": bool(cfg.audience)}, audience=cfg.audience, issuer=cfg.issuer)  # type: ignore[arg-type]
            return None
        except Exception:
            return None
    get_rate_limit_snapshot = None
    _get_request_payload = None
    verify_token = None
    verify_token_strict = None
    verify_ws = None
    rate_limit = None
    _payload_scopes = None
    validate_websocket_origin = None
    _apply_rate_limit = None
    rate_limit_problem = None
    http_burst = None
    _http_requests = None
    rate_limit_with = None
    require_nonce = None
    scope_rate_limit = None

__all__ = [
    "get_jwt_config",
    "JWTConfig",
    "jwt_decode",
    "decode_jwt",
    "get_rate_limit_snapshot",
    "_get_request_payload",
    "verify_token",
    "verify_token_strict",
    "verify_ws",
    "rate_limit",
    "_payload_scopes",
    "validate_websocket_origin",
    "_apply_rate_limit",
    "rate_limit_problem",
    "http_burst",
    "_http_requests",
    "rate_limit_with",
    "require_nonce",
    "scope_rate_limit",
    "verify_webhook",
    "sign_webhook",
    "rotate_webhook_secret",
]
